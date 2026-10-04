# SNS自動投稿

星座・恋愛ジャンルのアカウントで、Instagram と Threads に予約投稿する仕組み。

## 下書きを頼まれたとき

- `schedule/YYYY-MM-DD.yaml`（その週の月曜日の日付）に、`schedule/見本.yaml` と同じ形式で書く
- 必ず `approved: false` で書く。true にするのは本人の確認後
- 投稿枠: `threads_morning`（7:00）、`instagram`（20:00）、`threads_night`（21:00）
- 朝のThreads → 星座ジャンル（今日の運勢・ランキングなど）
- 夜のThreads → 恋愛ジャンル（あるある・アドバイス・問いかけ）
- Instagram → 星座×恋愛など保存されやすいテーマ。画像は `images/` にある本人の画像から選ぶ
  - 使える画像がなければ `image:` を空にして、どんな画像が合うかをコメントで書く
  - 同じ画像を続けて使わない
- 文字数: Threads は500文字以内、Instagram のキャプションは2200文字以内
- ハッシュタグ: Instagram は5〜10個程度。Threads はトピックタグ1つまで（なくてもよい）
- 「必ず〜になる」など断定的な表現や、不安をあおる表現は使わない
- 書き終わったら `python post.py --check` で確認する
