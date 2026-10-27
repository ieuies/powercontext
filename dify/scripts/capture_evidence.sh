#!/bin/bash
set -e
OUT=/work/evidence
rm -rf "$OUT"
mkdir -p "$OUT"

# 娓呯┖鏃ф暟鎹紝淇濊瘉璇佹嵁鍙鐜?for t in memories turns players; do
  mysql -h127.0.0.1 -P2881 -uroot -D tavern -e "DELETE FROM $t"
done

/work/pcenv/bin/python /work/dify/scripts/demo.py --base-url http://127.0.0.1:8080 > "$OUT/demo-output.txt" 2>&1

mysql -h127.0.0.1 -P2881 -uroot -D tavern -e \
  "SELECT player_id, name FROM players; SELECT id, kind, content, session_id FROM memories ORDER BY id; SELECT id, session_id, user_message, assistant_reply FROM turns ORDER BY id;" \
  > "$OUT/seekdb-rows.txt" 2>&1

# 鍐嶅仛涓€娆♀€滄柊浼氳瘽鈥濓紝璇佹槑璁板繂鍦ㄧ湡姝ｇ殑鏂颁細璇濋噷涔熻兘鍙洖
/work/pcenv/bin/python /work/dify/scripts/recall_session.py > "$OUT/recall-session-b.txt" 2>&1 || true

echo done
