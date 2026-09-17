# คู่มือติดตั้ง

ทำครั้งเดียวจบ ใช้เวลาประมาณ 40 นาที หลังจากนี้ระบบเดินเอง

---

## 1. Gemini API key (ฟรี)

1. เข้า https://aistudio.google.com/apikey
2. กด **Create API key** เลือกโปรเจกต์ใหม่
3. เก็บค่าที่ได้ไว้ เดี๋ยวเอาไปใส่ Secrets

โควต้าฟรีเหลือเฟือสำหรับวันละ 3 คลิป

---

## 2. เปิดใช้ YouTube Data API

1. เข้า https://console.cloud.google.com
2. สร้างโปรเจกต์ใหม่ ตั้งชื่ออะไรก็ได้
3. **APIs & Services → Library** → ค้นหา `YouTube Data API v3` → **Enable**

---

## 3. ตั้ง OAuth consent screen

1. **APIs & Services → OAuth consent screen**
2. User Type เลือก **External** → Create
3. กรอกชื่อแอป อีเมลติดต่อ ให้ครบ
4. หน้า Scopes ไม่ต้องเพิ่มอะไร กด Save ผ่านไป
5. หน้า Test users → ใส่อีเมลของตัวเอง

### ⚠️ ขั้นตอนที่ห้ามข้าม

กลับมาที่หน้า OAuth consent screen แล้วกด **PUBLISH APP** ให้สถานะเป็น **In production**

ถ้าปล่อยไว้เป็น *Testing* **refresh token จะหมดอายุทุก 7 วัน** ระบบจะพังเงียบ ๆ ทุกสัปดาห์
Google จะขึ้นเตือนว่าต้องผ่าน verification — ไม่ต้องสนใจ เพราะเราใช้กับบัญชีตัวเองเท่านั้น กด **Publish** ได้เลย

---

## 4. สร้าง OAuth client

1. **APIs & Services → Credentials → Create Credentials → OAuth client ID**
2. Application type เลือก **Desktop app**
3. ดาวน์โหลดไฟล์ JSON มาวางในโฟลเดอร์โปรเจกต์ (ชื่อจะขึ้นต้นด้วย `client_secret`)

---

## 5. ขอ refresh token

```bash
pip install -r requirements.txt
python tools/get_refresh_token.py
```

เบราว์เซอร์จะเปิดขึ้นมา → ล็อกอิน → **เลือกช่อง YouTube ที่จะให้อัปโหลด** → กดอนุญาต

สคริปต์จะพิมพ์ค่าสามตัวออกมา คัดลอกเก็บไว้ แล้ว**ลบไฟล์ `client_secret*.json` ทิ้ง**

> ค่าพวกนี้เป็นความลับระดับเดียวกับรหัสผ่าน ใครได้ไปอัปคลิปในช่องเราได้เลย
> อย่าวางในแชท อย่า commit ขึ้น git — ถ้าหลุดให้ไปเพิกถอนที่ https://myaccount.google.com/permissions ทันที

---

## 6. อัปขึ้น GitHub

```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin https://github.com/<ชื่อคุณ>/yt-auto.git
git push -u origin main
```

แนะนำให้ตั้งเป็น **public repo** เพราะ GitHub Actions ฟรีไม่จำกัดนาที (private ได้ 2,000 นาที/เดือน ซึ่งจะไม่พอ)
โค้ดเป็น public ไม่เป็นไร เพราะ key ทั้งหมดอยู่ใน Secrets ซึ่งไม่ถูกเปิดเผย

---

## 7. ใส่ Secrets

**Settings → Secrets and variables → Actions → New repository secret** ใส่ทีละตัว:

| ชื่อ | ค่า |
|---|---|
| `GEMINI_API_KEY` | จากขั้นที่ 1 |
| `YT_CLIENT_ID` | จากขั้นที่ 5 |
| `YT_CLIENT_SECRET` | จากขั้นที่ 5 |
| `YT_REFRESH_TOKEN` | จากขั้นที่ 5 |

---

## 8. เปิด GitHub Pages

**Settings → Pages → Source: Deploy from a branch → Branch: `main` / folder: `/docs`**

รอสักครู่จะได้ URL หน้า dashboard มา แล้วแก้ `REPO` ในไฟล์ `docs/index.html` ให้ตรงกับ repo ของคุณ

---

## 9. ทดลองรอบแรก

ไปที่แท็บ **Actions → publish → Run workflow**
- `count` = 1
- `upload` = ✅ (ค่า `privacy` ใน config.yaml เป็น `private` อยู่แล้ว คลิปจะยังไม่โผล่ต่อสาธารณะ)

รอประมาณ 5-8 นาที แล้วไปดูใน YouTube Studio

---

## 10. ก่อนเปิดสาธารณะจริง

1. ดูคลิปทดลองสัก 5-10 คลิป ปรับ `config.yaml` (เสียง สไตล์ภาพ ความเร็วพูด) จนพอใจ
2. ใส่เพลงประกอบใน `assets/music/` — ดูวิธีใน README ของโฟลเดอร์นั้น
3. เปลี่ยน `upload.privacy` ใน `config.yaml` เป็น `public`
4. ปล่อยให้ cron ทำงานเอง

---

## เวลาระบบพัง

GitHub จะส่งอีเมลเตือนอัตโนมัติเมื่อ workflow ล้ม และหน้า dashboard จะขึ้นไฟแดงพร้อมข้อความ error

| อาการ | สาเหตุที่พบบ่อย |
|---|---|
| `invalid_grant` | OAuth consent screen ยังเป็น Testing — กลับไปทำขั้นที่ 3 ให้จบ |
| `quotaExceeded` | อัปเกิน 6 คลิป/วัน หรือ retry หลายรอบ — รอรีเซ็ตเที่ยงคืน Pacific Time |
| ภาพไม่ขึ้น | Pollinations ล่ม ระบบลองซ้ำ 4 ครั้งแล้วยอมแพ้ — กด Retry ทีหลัง |
| ซับเป็นสี่เหลี่ยม | ไม่มีฟอนต์ไทยใน `assets/fonts/` |
| cron ไม่ทำงาน | repo เงียบเกิน 60 วัน — workflow `keepalive` ควรกันไว้ให้แล้ว |
