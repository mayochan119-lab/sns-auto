#!/bin/zsh
# このMacから5分ごとに呼ばれる。出すべき投稿があれば GitHub の「予約投稿」を動かす。
# （GitHub の予約実行は遅れたり飛ばされたりするため、その補助）
cd "$HOME/sns-auto" || exit 0
git pull -q --ff-only 2>/dev/null
due=$(.venv/bin/python post.py --due 2>/dev/null) || exit 0
gh="$HOME/.local/bin/gh"
# すでに動いている・待っている実行があれば何もしない
busy=$("$gh" run list --workflow post.yml --limit 5 --json status -q '[.[] | select(.status != "completed")] | length' 2>/dev/null)
[ "$busy" = "0" ] || exit 0
echo "$(date '+%F %T') kick: $due"
"$gh" workflow run post.yml
