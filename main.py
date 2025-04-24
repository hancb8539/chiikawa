import requests
import pandas as pd
import time
import re
from datetime import datetime, timezone, timedelta, date
from sheet import *
import os

SHOP   = "chiikawamarket.jp"
SHOP1 = "nagano-market.jp"
FULL_SHOP = "chiikawamarket.jp/zh-hant/collections/all/products"
FULL_SHOP1 = "nagano-market.jp/zh-hant/collections/all/products"
LIMIT  = 250
DELAY  = 1.0
DC_WEBHOOK = os.environ['dc_webhook']


def parse_re_tag(tag: str) -> date:
    """
    解析單一 RE 標籤，回傳對應的日期物件（不含時間）。
    支援 REYYYYMMDD（8）、REYYMMDD（6）、REYYMMDDHH（8）、REYYYYMMDDHH（10）。
    """
    nums = tag[2:]
    # YYYYMMDDHH (10)
    if len(nums) == 10:
        y = int(nums[0:4]); m = int(nums[4:6]); d = int(nums[6:8])
        # ignore hour nums[8:10] when building date
        return date(y, m, d)
    # YYYYMMDD (8) → 大多數 8 位以 20 開頭
    if len(nums) == 8 and nums.startswith(("20","19")):
        y = int(nums[0:4]); m = int(nums[4:6]); d = int(nums[6:8])
        return date(y, m, d)
    # YYMMDDHH (8) → 不是 20xx 開頭時
    if len(nums) == 8:
        y = 2000 + int(nums[0:2]); m = int(nums[2:4]); d = int(nums[4:6])
        # ignore hour nums[6:8]
        return date(y, m, d)
    # YYMMDD (6)
    if len(nums) == 6:
        y = 2000 + int(nums[0:2]); m = int(nums[2:4]); d = int(nums[4:6])
        return date(y, m, d)
    # 其它格式，回今天保底
    return datetime.now(timezone(timedelta(hours=8))).date()


def extract_re_tags_and_filter(tags_list):
    """
    從 tags_list 過濾出所有 RE 標籤，解析它們的日期，
    並分成所有 re_tags / future_re_tags。
    """
    # 只抓 RE + (6,8,10) 位數字
    pattern = re.compile(r"^RE(\d{6}|\d{8}|\d{10})$")
    re_tags = [t for t in tags_list if pattern.match(t)]

    # 取今天 (UTC+8)
    today = datetime.now(timezone(timedelta(hours=8))).date()
    future = []
    for t in re_tags:
        dt = parse_re_tag(t)
        if dt >= today:
            # 格式化回原字串
            future.append(t)
    return re_tags, future


def catch():
    page = 1
    records = []
    while True:
        r = requests.get(
            f"https://{SHOP1}/zh-hant/products.json",
            params={"limit": LIMIT, "page": page, "fields": "handle,tags,images, title"}
        )
        r.raise_for_status()
        batch = r.json().get("products", [])
        if not batch:
            break
    
        for p in batch:
            handle    = p["handle"]
            title    = p["title"] 
            tags_list = p.get("tags", [])
            images    = p.get("images", [])
            re_all, re_future = extract_re_tags_and_filter(tags_list)
            image_url = images[0]["src"] if images else ""

            if re_future:
                future_dates = [ parse_re_tag(t).strftime("%Y-%m-%d") for t in re_future ]
                records.append({
                    "title":   title,
                    "handle":   handle,
                    "tags":     "|".join(tags_list),
                    "future_re_tags":  "|".join(future_dates),
                    "count_future":    len(future_dates),
                    "URL": f"https://{FULL_SHOP1}/{handle}",
                    "image_url":       image_url,
                })
    
        print(f"第 {page} 頁抓到 {len(batch)} 筆")
        page += 1
        time.sleep(DELAY)
    
    # 轉成 DataFrame 並寫出 UTF-8 BOM CSV
    df = pd.DataFrame(records)
    #df.to_csv("all_tags_pandas_with_re.csv", index=False, encoding="utf-8-sig")

    return df, records
    #print("✅ 已將結果存到 all_tags_pandas_with_re.csv")

if __name__ == "__main__":
    retult, records = catch()
    
    send_products_embed(DC_WEBHOOK, records)
    
    scope(retult)

        
    