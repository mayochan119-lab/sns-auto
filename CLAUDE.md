# SNS自動投稿

星座アカウント（seiza）と恋愛アカウント（renai）の2つで、Instagram と Threads に予約投稿する仕組み。

## 下書きを頼まれたとき

- `schedule/YYYY-MM-DD.yaml`（その週の月曜日の日付）に、`schedule/見本.yaml` と同じ形式で書く
- 必ず `approved: false` で書く。true にするのは本人の確認後
- アカウントと投稿枠は `accounts.yaml` を見る（各アカウントに threads_morning 7:00 / instagram 20:00 / threads_night 21:00）
- seiza → 星座ジャンル（今日の運勢・ランキング・星座ごとの性格など）
- renai → 恋愛ジャンル（あるある・アドバイス・問いかけ・星座別の恋愛傾向など）
- 朝は短く明るく、夜は共感・語りかけ寄りにする
- Instagram は保存されやすいテーマ。画像は `images/seiza/` `images/renai/` にある本人の画像から選ぶ
  - 複数枚投稿は、1投稿分の画像を1つのフォルダ（例: `images/seiza/0108_ランキング/`）にまとめ、`images: [そのフォルダ]` と書く。並び順はファイル名順。インスタは最大10枚
  - 投稿済みの画像・フォルダは `posted.json` と過去の予定ファイルで確認できる
  - 使える画像がなければ `image:` を空にして、どんな画像が合うかをコメントで書く
  - 同じ画像を続けて使わない
- 文字数: Threads は500文字以内、Instagram のキャプションは2200文字以内
- ハッシュタグ: Instagram は5〜10個程度。Threads はトピックタグ1つまで（なくてもよい）
- 「必ず〜になる」など断定的な表現や、不安をあおる表現は使わない
- 書き終わったら `python post.py --check` で確認する
