#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
クイズ回答・自動集計プロトタイプ（クラウド版）
サーバーは学校のタブレットではなく、インターネット上のクラウドで動く。
親機・子機とも、発行されたURLをブラウザで開くだけで参加できる。
タブレット側にPython・exe・インストール作業は一切不要。
Python標準機能のみ使用。ポートは環境変数 PORT があればそれに従う
（クラウド各社の仕様。無ければ 8000）。
"""
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8000"))

QUESTIONS = [
    {"q": "3 ＋ 4 ＝ ?", "choices": ["6", "7", "8", "9"], "answer": 1},
    {"q": "9 － 5 ＝ ?", "choices": ["3", "5", "4", "6"], "answer": 2},
    {"q": "2 × 3 ＝ ?", "choices": ["5", "7", "8", "6"], "answer": 3},
    {"q": "10 ÷ 2 ＝ ?", "choices": ["5", "4", "6", "7"], "answer": 0},
    {"q": "7 ＋ 8 ＝ ?", "choices": ["13", "14", "16", "15"], "answer": 3},
    {"q": "15 － 6 ＝ ?", "choices": ["8", "9", "10", "7"], "answer": 1},
    {"q": "4 × 5 ＝ ?", "choices": ["20", "15", "25", "9"], "answer": 0},
    {"q": "100 ＋ 23 ＝ ?", "choices": ["120", "130", "123", "113"], "answer": 2},
    {"q": "50 － 25 ＝ ?", "choices": ["20", "30", "35", "25"], "answer": 3},
    {"q": "6 × 6 ＝ ?", "choices": ["30", "36", "42", "26"], "answer": 1},
]
LETTERS = ["A", "B", "C", "D"]

lock = threading.Lock()
state = {}


def reset_state():
    state.clear()
    state.update({
        "phase": "waiting",   # waiting | open | closed | revealed | finished
        "qindex": 0,
        "teams": {},          # team(str) -> {"score": int}
        "answers": {},        # team(str) -> choice index (現在の問題)
        "scored": False,      # 現在の問題を採点済みか
        "last_result": {},    # team(str) -> True/False（正解発表後の表示用）
    })


reset_state()


def public_state():
    with lock:
        q = None
        if state["phase"] != "finished" and state["qindex"] < len(QUESTIONS):
            cur = QUESTIONS[state["qindex"]]
            q = {"number": state["qindex"] + 1, "total": len(QUESTIONS),
                 "text": cur["q"], "choices": cur["choices"]}
            if state["phase"] == "revealed":
                q["answer"] = cur["answer"]
        ranking = sorted(
            ({"team": t, "score": d["score"]} for t, d in state["teams"].items()),
            key=lambda x: (-x["score"], int(x["team"])),
        )
        return {
            "phase": state["phase"],
            "question": q,
            "joined": sorted(state["teams"].keys(), key=lambda x: int(x)),
            "answered": sorted(state["answers"].keys(), key=lambda x: int(x)),
            "answers_detail": dict(state["answers"]) if state["phase"] == "revealed" else {},
            "last_result": dict(state["last_result"]),
            "ranking": ranking,
        }


CLIENT_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>クイズ回答（子機）</title>
<style>
body{font-family:sans-serif;margin:0;background:#0f2540;color:#fff;text-align:center}
.wrap{max-width:860px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:8px 0}
.big{font-size:40px;font-weight:bold;margin:18px 0;line-height:1.3}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}
button{font-size:22px;padding:18px 6px;border-radius:12px;border:none;background:#2e75b6;color:#fff;cursor:pointer}
button:disabled{opacity:.45;cursor:default}
.teambtn{background:#444}
.teambtn.sel{background:#e8a33d;color:#222;font-weight:bold}
.choices{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:16px}
.choice{font-size:30px;padding:30px 8px}
.cA{background:#d64545}.cB{background:#2e9e5b}.cC{background:#2e75b6}.cD{background:#e8a33d;color:#222}
.note{font-size:18px;opacity:.9}
.ok{color:#7ee2a0;font-weight:bold}.ng{color:#ff9a9a;font-weight:bold}
</style></head><body><div class="wrap">
<h1>クイズ回答 ― チーム<span id="tn"></span></h1>
<div id="main"></div>
</div>
<script>
let team = localStorage.getItem("quiz-team") || "";
const main = document.getElementById("main");
function post(path, obj){ return fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(obj||{})}); }
async function join(t){ team=t; localStorage.setItem("quiz-team",t); await post("/api/join",{team:t}); render(); }
async function answer(i){ await post("/api/answer",{team:team, choice:i}); render(); }
async function render(){
  let s; try{ s = await (await fetch("/api/state")).json(); }catch(e){ return; }
  document.getElementById("tn").textContent = team ? "（"+team+"）" : "";
  if(!team){
    let h = '<p class="note">まず自分のチーム番号を選んでください</p><div class="grid">';
    for(let i=1;i<=20;i++) h += '<button class="teambtn" onclick="join(\''+i+'\')">'+i+'</button>';
    main.innerHTML = h + "</div>"; return;
  }
  const answered = s.answered.includes(team);
  if(s.phase==="waiting"){ main.innerHTML = '<p class="big">待機中</p><p class="note">司会が問題を出すまで待ってください</p>'; return; }
  if(s.phase==="finished"){ main.innerHTML = '<p class="big">終了！</p><p class="note">おつかれさまでした。結果は集計画面を見てください</p>'; return; }
  const q = s.question;
  let h = '<p class="note">第'+q.number+'問 ／ 全'+q.total+'問</p><p class="big">'+q.text+'</p>';
  if(s.phase==="open"){
    if(answered){ h += '<p class="big ok">回答ずみ</p><p class="note">他のチームの回答を待っています…</p>'; }
    else{
      h += '<div class="choices">';
      q.choices.forEach((c,i)=>{ h += '<button class="choice c'+'ABCD'[i]+'" onclick="answer('+i+')">'+'ABCD'[i]+'：'+c+'</button>'; });
      h += '</div>';
    }
  } else if(s.phase==="closed"){
    h += answered ? '<p class="big">回答ずみ</p><p class="note">締め切られました。正解発表を待ってください</p>'
                  : '<p class="big">締め切り</p><p class="note">この問題は回答できませんでした</p>';
  } else if(s.phase==="revealed"){
    const mine = s.answers_detail[team];
    const res = s.last_result[team];
    h += '<p class="note">正解は '+'ABCD'[q.answer]+'：'+q.choices[q.answer]+'</p>';
    if(mine===undefined) h += '<p class="big">未回答</p>';
    else h += res ? '<p class="big ok">正解！ +1点</p>' : '<p class="big ng">残念…</p><p class="note">あなたの回答：'+'ABCD'[mine]+'：'+q.choices[mine]+'</p>';
  }
  main.innerHTML = h;
}
setInterval(render, 800); render();
</script></body></html>"""

HOST_HTML = r"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>司会・集計（親機）</title>
<style>
body{font-family:sans-serif;margin:0;background:#14202e;color:#fff}
.wrap{max-width:980px;margin:0 auto;padding:16px}
h1{font-size:22px}
.big{font-size:34px;font-weight:bold;margin:10px 0}
button{font-size:18px;padding:12px 18px;border-radius:10px;border:none;background:#2e75b6;color:#fff;cursor:pointer;margin:4px}
button.warn{background:#d64545}
button.go{background:#2e9e5b}
table{border-collapse:collapse;width:100%;margin-top:10px;background:#1d2f42}
th,td{border:1px solid #3a5068;padding:8px 12px;font-size:18px;text-align:left}
th{background:#2e75b6}
.note{opacity:.85}
</style></head><body><div class="wrap">
<h1>司会・集計画面（親機）</h1>
<div id="status"></div>
<div>
<button class="go" onclick="ctl('start')">▶ 問題を開始</button>
<button onclick="ctl('close')">回答を締め切る</button>
<button class="go" onclick="ctl('reveal')">正解発表（自動採点）</button>
<button onclick="ctl('next')">次の問題へ</button>
<button class="warn" onclick="if(confirm('最初からやり直しますか？')) ctl('reset')">リセット</button>
</div>
<div id="rank"></div>
</div>
<script>
function post(path,obj){ return fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(obj||{})}); }
async function ctl(a){ await post("/api/control",{action:a}); render(); }
async function render(){
  let s; try{ s = await (await fetch("/api/state")).json(); }catch(e){ return; }
  const names = {waiting:"待機中", open:"回答受付中", closed:"締め切り済み", revealed:"正解発表", finished:"終了"};
  let h = "";
  if(s.question) h += '<p class="big">第'+s.question.number+'問：'+s.question.text+'</p>';
  h += '<p class="note">状態：'+names[s.phase]+' ／ 参加中：'+s.joined.length+'チーム ／ 回答済み：'+s.answered.length+'チーム（'+s.answered.join("、")+'）</p>';
  if(s.phase==="revealed" && s.question) h += '<p class="note">正解：'+'ABCD'[s.question.answer]+'：'+s.question.choices[s.question.answer]+'</p>';
  document.getElementById("status").innerHTML = h;
  let r = '<h2>順位表（自動集計）</h2><table><tr><th>順位</th><th>チーム</th><th>得点</th></tr>';
  s.ranking.forEach((row,i)=>{ r += '<tr><td>'+(i+1)+'</td><td>チーム'+row.team+'</td><td>'+row.score+'</td></tr>'; });
  if(!s.ranking.length) r += '<tr><td colspan="3">まだチームが参加していません</td></tr>';
  document.getElementById("rank").innerHTML = r + "</table>";
}
setInterval(render, 800); render();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, CLIENT_HTML, "text/html; charset=utf-8")
        elif self.path == "/host":
            self._send(200, HOST_HTML, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, json.dumps(public_state(), ensure_ascii=False))
        else:
            self._send(404, "{}")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            data = {}
        with lock:
            if self.path == "/api/join":
                t = str(data.get("team", ""))
                if t.isdigit() and 1 <= int(t) <= 20:
                    state["teams"].setdefault(t, {"score": 0})
            elif self.path == "/api/answer":
                t = str(data.get("team", ""))
                c = data.get("choice")
                if (state["phase"] == "open" and t in state["teams"]
                        and t not in state["answers"]
                        and isinstance(c, int) and 0 <= c <= 3):
                    state["answers"][t] = c
            elif self.path == "/api/control":
                a = data.get("action")
                if a == "reset":
                    reset_state()
                elif a == "start" and state["phase"] == "waiting":
                    state["phase"] = "open"
                    state["answers"] = {}
                    state["scored"] = False
                    state["last_result"] = {}
                elif a == "close" and state["phase"] == "open":
                    state["phase"] = "closed"
                elif a == "reveal" and state["phase"] in ("open", "closed"):
                    cur = QUESTIONS[state["qindex"]]
                    if not state["scored"]:
                        res = {}
                        for t, c in state["answers"].items():
                            ok = (c == cur["answer"])
                            res[t] = ok
                            if ok:
                                state["teams"][t]["score"] += 1
                        state["last_result"] = res
                        state["scored"] = True
                    state["phase"] = "revealed"
                elif a == "next" and state["phase"] == "revealed":
                    if state["qindex"] + 1 >= len(QUESTIONS):
                        state["phase"] = "finished"
                    else:
                        state["qindex"] += 1
                        state["phase"] = "open"
                        state["answers"] = {}
                        state["scored"] = False
                        state["last_result"] = {}
        self._send(200, json.dumps(public_state(), ensure_ascii=False))


if __name__ == "__main__":
    # クラウド上では常に全方向から待ち受ける。接続は各社のHTTPS経由で届くため、
    # 学校側のファイアウォール（内向き接続）には一切当たらない。
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("=" * 56)
    print("クイズ集計サーバー起動（クラウド版）")
    print(f"port: {PORT}")
    print("子機（回答）      : 発行されたURL を開く")
    print("親機（司会・集計）: 発行されたURL の後ろに /host を付ける")
    print("=" * 56, flush=True)
    server.serve_forever()
