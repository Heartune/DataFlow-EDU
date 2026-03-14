# 1) 设定目标文件的正则!!!!注意，这个脚本只能针对性修改单文件。
FILE_REGEX='static/images/Face.png$'

# 2) 找出 HEAD 中该文件的 blob（最新版本）
git ls-tree -r -z HEAD --full-tree \
| sed -zn 's/^.* blob \([0-9a-f]\{40\}\)\t\(.*\)$/\1 \2/p' \
| grep -Ei " ${FILE_REGEX}" \
| awk '{print $1}' \
| sort -u > /tmp/head_keep_ids.txt

# 3) 找出历史上匹配路径的所有 blob
git rev-list --objects --all \
| grep -Ei " ${FILE_REGEX}" \
| awk '{print $1}' \
| sort -u > /tmp/all_face_ids.txt

# 4) 生成“要删除的旧版本 blob = 历史全部 - HEAD 保留”
comm -23 /tmp/all_face_ids.txt /tmp/head_keep_ids.txt > ./face_old_ids.txt

echo fuck

# 5) 剥离这些旧 blob（不会影响 HEAD 最新版）
if [ -s ./face_old_ids.txt ]; then
  git filter-repo --force \
    --strip-blobs-with-ids ./face_old_ids.txt \
    --prune-empty=always
else
  echo "没有需要剥离的旧版本（可能只有一个版本，或路径不匹配）。"
fi