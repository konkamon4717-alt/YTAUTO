#!/usr/bin/env bash
# บันทึกผลของรอบนี้กลับเข้า repo
#
#   tools/commit_back.sh "<ข้อความ commit>" <path> [path...]
#
# ทุก workflow เขียนผลกลับเข้า repo เดียวกัน และหลาย job วิ่งต่อกันในนาทีเดียวกัน
# ตัวที่ push ทีหลังจะเจอว่า main ขยับไปแล้ว ถ้า rebase ไม่ผ่านแล้วปล่อยเลยตามเลย
# ผลของรอบนั้นจะหายไปเงียบ ๆ ซึ่งเคยทำให้ไฟล์ประวัติไม่เคยถูกบันทึก
# แล้วตัวกันโพสต์ซ้ำตาบอด ลงคลิปเรื่องเดิมวันละสามรอบ
#
# จึงต้องลองใหม่หลายครั้ง และถ้าสุดท้ายยังไม่ได้ต้องทำให้ job แดง
# ไม่ใช่เขียว เพราะสถานะที่หายไปคือสิ่งที่รอบถัดไปใช้ตัดสินใจ
set -euo pipefail

MESSAGE="$1"
shift

BRANCH="${GITHUB_REF_NAME:-main}"

git config user.name  "yt-auto bot"
git config user.email "actions@github.com"

git add "$@" 2>/dev/null || true
if git diff --staged --quiet; then
  echo "ไม่มีอะไรเปลี่ยน ไม่ต้องบันทึก"
  exit 0
fi
git commit -m "$MESSAGE"

for attempt in 1 2 3 4 5; do
  git fetch -q origin "$BRANCH"
  if git rebase -q "origin/$BRANCH"; then
    if git push -q origin "HEAD:$BRANCH"; then
      echo "บันทึกแล้ว (ครั้งที่ $attempt)"
      exit 0
    fi
  else
    git rebase --abort || true
  fi
  # หน่วงแบบสุ่มเพื่อไม่ให้สอง job ที่ชนกันมาลองใหม่พร้อมกันซ้ำอีก
  sleep $(( (RANDOM % 8) + 4 ))
done

echo "::error::บันทึกผลกลับ repo ไม่สำเร็จหลังลองห้าครั้ง — รอบถัดไปจะไม่รู้ว่ารอบนี้ทำอะไรไป"
exit 1
