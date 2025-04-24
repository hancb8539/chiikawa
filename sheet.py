import requests
from PIL import Image
from io import BytesIO
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timezone, timedelta
import time

# Discord embed 限制常數
MAX_EMBEDS     = 10
MAX_TITLE      = 256
MAX_DESC       = 2048
MAX_FIELD_NAME = 256
MAX_FIELD_VAL  = 1024

def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
  
def send_products_embed(webhook_url: str, products: list):
  def build_embed(p):
    title = truncate(p["title"], MAX_TITLE)
    desc  = truncate(p["future_re_tags"], MAX_DESC)
    return {
        "title": title,
        "url":   p["URL"],
        "color": 0xEAAA00,
        "fields": [
            {
                "name":  "補貨日期",
                "value": desc or "無",
                "inline": False
            }
        ],
        "thumbnail": {"url": p["image_url"]}
    }
  if products == []:
      embeds = {
        "title": "❌ 沒有商品可以發送！",
      }
      payload = {"username": "兔兔", "embeds": [embeds]}
      r = requests.post(webhook_url, json=payload)
      r.raise_for_status()
      print("❌ 沒有商品可以發送！")
  # 切 batches
  for i in range(0, len(products), MAX_EMBEDS):
      batch = products[i : i + MAX_EMBEDS]
      embeds = [build_embed(p) for p in batch]
      payload = {"username": "兔兔", "embeds": embeds}

      r = requests.post(webhook_url, json=payload)
      try:
          r.raise_for_status()
      except requests.exceptions.HTTPError:
          # 印出錯誤內容，方便除錯
          print("❌ Webhook 發送失敗:", r.status_code, r.text)
          # 如果是 429（Too Many Requests），可以加上重試機制
          if r.status_code == 429:
              retry = int(r.json().get("retry_after", 1))
              print(f"等待 {retry} 秒後重試…")
              time.sleep(retry)
              r = requests.post(webhook_url, json=payload)
              r.raise_for_status()
      else:
          print(f"✅ 已發送 {len(embeds)} 個 embeds (batch {i//MAX_EMBEDS+1})")
  
def scope(df):
  scope = [
      "https://spreadsheets.google.com/feeds",
      "https://www.googleapis.com/auth/drive"
  ]

  creds = ServiceAccountCredentials.from_json_keyfile_name(
      "service_account.json", scope)
  gc = gspread.authorize(creds)

  SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1MT7QDgOGlB62jSrUNT1Q5vbB_2YXYzA4SqPwXhxkWvM/edit"
  sh = gc.open_by_url(SPREADSHEET_URL)

  tz = timezone(timedelta(hours=8))                 # 建立 UTC+8 時區
  now = datetime.now(tz)                            # 取當前 UTC+8 時間
  sheet_name = now.strftime("%Y%m%d%H%M") 
  rows = df.shape[0] + 1
  cols = df.shape[1]
  new_ws = sh.add_worksheet(title=sheet_name, rows=str(rows), cols=str(cols))
  # 取得這個 sheet 的 sheetId
  sheet_id = new_ws._properties['sheetId']
  # 用 batch_update 呼叫 Sheets API，更新這個頁面的 index 到 0
  sh.batch_update({
      "requests": [
          {
              "updateSheetProperties": {
                  "properties": {
                      "sheetId": sheet_id,
                      "index": 0
                  },
                  "fields": "index"
              }
          }
      ]
  })

  headers = df.columns.tolist()
  # 找到 image_url 在第幾欄
  try:
      img_idx = headers.index("image_url")
  except ValueError:
      img_idx = None

  # 把 header 加進去
  values = [headers]
  max_img_width = 0
  row_heights = {}
  
  for r, row in enumerate(df.values.tolist(), start=1):
      cells = row[:]  # copy
      if img_idx is not None:
          url = cells[img_idx]
          if url:
              try:
                  resp = requests.get(url, timeout=10)
                  img = Image.open(BytesIO(resp.content))
                  h, w = 150, 150
                  # 更新最大寬度
                  if w > max_img_width:
                      max_img_width = w
                  # 記錄這一行應該的高度
                  row_heights[r] = h
                  # 用 mode=4 並指定高寬
                  cells[img_idx] = f'=IMAGE("{url}",4,{h},{w})'
              except Exception:
                  # 若有錯，就退回成簡單 IMAGE()
                  cells[img_idx] = f'=IMAGE("{url}")'
      values.append(cells)
    
  new_ws.update("A1", values, value_input_option="USER_ENTERED")

  # 5. 產生 batch_update 請求，調整列高與欄寬
  requests_list = []
  # 調整每一筆資料所在的列高（0-based 第 r 列到 r+1）
  for r, h in row_heights.items():
      requests_list.append({
          "updateDimensionProperties": {
              "range": {
                  "sheetId":   sheet_id,
                  "dimension": "ROWS",
                  "startIndex": r,      # header 在 0，資料第 1 列 → startIndex=1
                  "endIndex":   r + 1
              },
              "properties": {"pixelSize": h},
              "fields":     "pixelSize"
          }
      })
  # 調整整個圖片欄的寬度
  if img_idx is not None and max_img_width > 0:
      requests_list.append({
          "updateDimensionProperties": {
              "range": {
                  "sheetId":   sheet_id,
                  "dimension": "COLUMNS",
                  "startIndex": img_idx,
                  "endIndex":   img_idx + 1
              },
              "properties": {"pixelSize": max_img_width},
              "fields":     "pixelSize"
          }
      })

  # 6. 執行 batch_update
  if requests_list:
      sh.batch_update({"requests": requests_list})

  print(f"✅ 分頁「{sheet_name}」已建立，並自動調整圖片儲存格大小！")
  

  
