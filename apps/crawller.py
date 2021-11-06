# -*- coding: utf-8 -*-
from selenium.common.exceptions import NoSuchElementException
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timedelta, timezone
from selenium.webdriver.common.by import By
from pymongo.collection import Collection
from pymongo import MongoClient
from selenium import webdriver
from bs4 import BeautifulSoup
from urllib import parse
import mongoengine as me
import uuid
import csv
import time
import re
import os


client = MongoClient(os.environ.get('DB_PATH'))
if client.HOST == "localhost":
    os.popen("mongod")
db = client.get_database("member_card")
articles: Collection = db.get_collection("articles")
members: Collection = db.get_collection("members")
members_blogs = members.find({}).sort("blog_type")


class Member(me.Document):
    uid = me.UUIDField(binary=False)
    username = me.StringField()
    blog = me.URLField()
    blog_type = me.StringField()
    image = me.URLField()
    member_card = me.StringField()
    hobby = me.ListField()
    specialty = me.ListField()


class Post(me.Document):
    name = me.StringField()
    author = me.StringField()
    title = me.StringField()
    site_name = me.StringField()
    description = me.StringField()
    url = me.URLField()
    image = me.URLField()
    registered = me.DateTimeField()
    modified = me.DateTimeField()
    shared = me.IntField()
    comment = me.IntField()


def inject_members():
    with open("data/blog.csv", newline="",
              encoding="utf-8", mode="r") as input_file:
        input_file.__next__()
        for line in input_file.readlines():
            [name, blog1, blog2, btype] = line.strip().split(',')
            if blog1:
                mem = Member(
                    uid=uuid.uuid4(),
                    username=name,
                    blog=blog1,
                    blog_type=btype
                )
                members.update_one({"username": name}, {'$set': mem.to_mongo()}, upsert=True)
            if blog2.strip():
                mem = Member(
                    uid=uuid.uuid4(),
                    username=name,
                    blog=blog2,
                    blog_type=btype
                )
                members.update_one({"username": name}, {'$set': mem.to_mongo()}, upsert=True)


def member_card():
    with open("data/member.csv", newline="",
              encoding="utf-8", mode="r") as input_file:
        input_file.__next__()
        reader = csv.reader(input_file)
        for line in reader:
            [name, blog, hobby, specialty] = line[:4]
            hobby = hobby.replace(', ', ',')
            hobby = hobby.replace(', ', ',')
            specialty = specialty.replace(', ', ',')
            specialty = specialty.replace(', ', ',')
            image = ""
            for f in os.listdir("../static/img"):
                if f.startswith(name):
                    image = f
            mem = Member(
                username=name,
                image="/static/img/"+image,
                blog=blog,
                hobby=hobby.split(','),
                specialty=specialty.split(',')
            )
            members.update_one({"username": name}, {'$set': mem.to_mongo()}, upsert=True)


def tistory_blog():
    print("daum-tistory blog detected")
    driver = webdriver.Chrome()
    tistory_members = members.find({"blog_type": "tistory"}, {"_id": False})
    tistory_urls = []
    for member in tistory_members:
        if member["blog"].strip():
            tistory_urls.append((member['username'], member['blog'], member["blog_type"]))
    for name, url, types in tistory_urls:
        target_part = parse.urlparse(url+"sitemap")
        target = parse.urlunparse(target_part)
        driver.get(target)
        res = driver.page_source
        soup = BeautifulSoup(res, 'html.parser')
        regex = re.compile(url+r"\d+")
        url_list = sorted(regex.findall(soup.text))
        if not url_list:
            regex = re.compile(url+"entry/" + r"[\-%\w\d]+")
            url_list = sorted(regex.findall(soup.text))
        members.update_one({"username": name}, {"$set": {"blog_list": url_list}}, upsert=True)
    driver.quit()


def velog_blog():
    print("velo-pert blog detected")
    driver = webdriver.Chrome()
    velog_members = members.find({"blog_type": "velog"}, {"_id": False})
    velog_urls = []
    for mem in velog_members:
        if mem["blog"].strip():
            velog_urls.append((mem['username'], mem['blog'], mem["blog_type"]))
    for name, url, types in velog_urls:
        driver.get(url)
        scroll_to_bottom = "window.scrollTo(0, document.body.scrollHeight);"
        get_window_height = "return document.body.scrollHeight"
        last_height = driver.execute_script(get_window_height)
        while True:
            driver.execute_script(scroll_to_bottom)
            time.sleep(1)
            new_height = driver.execute_script(get_window_height)
            if new_height == last_height:
                break
            last_height = new_height
        contents = driver.find_elements(By.XPATH, '//*[@id="root"]/div[2]/div[3]/div[4]/div[3]/div/div/a')
        url_list =[]
        for content in contents:
            url_list.append(content.get_attribute('href'))
        members.update_one({"username": name}, {"$set": {"blog_list": sorted(url_list)}}, upsert=True)
    driver.quit()
    

def crawl_post():
    print("let's crawl!!!!!")
    driver = webdriver.Chrome()
    for student in members_blogs:
        if student.get("blog_list"):
            if student["blog_type"] == "tistory":
                for url in student["blog_list"]:
                    if list(articles.find({"url": url})):
                        continue
                    try:
                        driver.get(url)
                        title = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:title"]')\
                            .get_attribute('content')
                        author = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:article:author"]')\
                            .get_attribute('content')
                        site_name = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:site_name"]')\
                            .get_attribute('content')
                        reg_date = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:regDate"]')\
                            .get_attribute('content')
                        modified_time = driver.find_element(By.CSS_SELECTOR, 'meta[property="article:modified_time"]')\
                            .get_attribute('content')
                        image = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:image"]')\
                            .get_attribute('content')
                        description = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:description"]')\
                            .get_attribute('content')

                        post = Post(
                            name=student['username'],
                            author=author,
                            url=url,
                            title=title,
                            site_name=site_name,
                            registered=get_time(reg_date),
                            modified=get_time(modified_time),
                            image=image,
                            description=description,
                            shared=0,
                            comment=0
                        )
                        put_doc(post)
                        print(get_time(reg_date))
                    except NoSuchElementException:
                        pass
            else:
                for url in student["blog_list"]:
                    if list(articles.find({"url": url})):
                        continue
                    try:
                        driver.get(url)
                        title = driver.title
                        author = driver.find_element(By.CSS_SELECTOR, 'span.username').text
                        site_name = driver.find_element(By.CSS_SELECTOR, 'a.user-logo').text
                        reg_date = driver.find_element(By.CSS_SELECTOR, 'div.information > span:nth-child(3)').text
                        image = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:image"]')\
                            .get_attribute('content')
                        description = driver.find_element(By.CSS_SELECTOR, 'meta[property="og:description"]')\
                            .get_attribute('content')
                        post = Post(
                            name=student['username'],
                            author=author,
                            url=url,
                            title=title,
                            site_name=site_name,
                            registered=get_time(reg_date),
                            image=image,
                            description=description,
                            shared=0,
                            comment=0
                        )
                        put_doc(post)
                        print(get_time(reg_date))
                    except NoSuchElementException:
                        pass
    driver.quit()


def get_time(time_string) -> datetime:
    timezone(timedelta(hours=+9))
    regex0 = re.compile(r"[약 ]*(\d{1,2})일 전")
    regex00 = re.compile(r"[약 ]*(\d{1,2})시간 전")
    regex1 = re.compile(r"(\d{4})년 (\d{1,2})월 (\d{1,2})일")
    regex2 = re.compile(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})")
    if time_string == "어제":
        return datetime.now() - timedelta(days=1)
    if regex0.match(time_string):
        n = int(regex0.match(time_string).groups()[0])
        return datetime.now() - timedelta(days=n)
    elif regex00.match(time_string):
        n = int(regex00.match(time_string).groups()[0])
        return datetime.now() - timedelta(hours=n)
    elif regex1.match(time_string):
        year, month, day = map(int, regex1.match(time_string).groups())
        return datetime(year, month, day)
    elif regex2.match(time_string):
        year, month, day, hour, minute, sec = map(int, regex2.match(time_string).groups())
        return datetime(year, month, day, hour, minute, sec)
    else:
        return datetime.fromisoformat(time_string)


def put_doc(post):
    print(post.description)
    articles.update_one({"url": post['url']}, {"$set": post.to_mongo()}, upsert=True)


if __name__ == '__main__':
    sched.add_job(inject_members, 'cron', hour="9,21", id="test1")
    sched.add_job(member_card, 'cron', hour="10,22", id="test2")
    sched.add_job(tistory_blog, 'cron', minute="0", id="test3")
    sched.add_job(velog_blog, 'cron', minute="10", id="test4")
    sched.add_job(crawl_post, 'cron', minute="20", id="test5")
