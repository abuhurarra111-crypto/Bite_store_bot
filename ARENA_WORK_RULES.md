# Bite Store Bot — Arena Working Rules

Owner-approved workflow rules. Read this file before every task in this workspace.

## Communication

1. Owner se Roman Urdu mein clear aur short baat karni hai.
2. Har task ke end par table summary deni hai.
3. Har task ke end par batana hai:
   - kya investigate kiya;
   - root cause kya tha;
   - kya files/code/DB change hua;
   - kya tests kiye aur unka result;
   - deploy/GitHub status;
   - future improvement suggestions.
4. Kabhi jhoot nahi bolna. Jo live verify na ho, usay clearly unverified kehna hai.
5. Tests pass hue baghair "fixed" nahi kehna.

## Bug Fix / Feature Workflow

1. Pehle root cause investigate karna hai; guess-based patch nahi lagana.
2. Existing behavior aur related flows ka regression impact check karna hai.
3. Relevant automated/static/functional tests khud chalane hain.
4. Runtime code/config change ke baad:
   - fixed Arena branch par commit karna;
   - isi branch ko GitHub par push karna;
   - Railway par deploy karna;
   - deployment logs/startup/health verify karna;
   - failure ho to root cause fix ya safe rollback karna.
5. Documentation-only change ke liye Railway deploy zaroori nahi, kyun ke runtime artifact change nahi hota.
6. Secrets/tokens ko code, DB, logs, commits ya chat response mein expose/save nahi karna.

## Ready Database Workflow

Jab task database behavior/schema/data ko affect kare, owner ki supplied source DB par final ready copy banani hai:

1. Original DB ko modify nahi karna; working copy aur backup banana.
2. Current application migrations working copy par run karni hain.
3. `PRAGMA integrity_check` pass karna lazmi hai.
4. `PRAGMA foreign_key_check` aur expected schema/table checks karne hain.
5. Relevant restore/startup/functional tests chalane hain.
6. Sirf successful verification ke baad ready DB deliver karni hai.
7. Exact DB file path, size/hash, tests aur restore notes summary mein dene hain.
8. Agar source DB available/downloadable na ho to ready DB ka jhoota claim nahi karna.

## Safety Boundaries

1. 100% zero-risk guarantee nahi deni; evidence-based test status report karna hai.
2. Destructive DB/deploy operation se pehle backup/rollback path rakhna hai.
3. Live external APIs, Telegram, supplier, payment ya Railway verification unavailable ho to limitation clearly batani hai.
4. Repository session ki fixed branch `arena/01a02a8c-bite-store-bot` hi use karni hai.
