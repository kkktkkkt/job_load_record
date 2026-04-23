@echo off
cd /d "%~dp0"

echo [1/2] ライブラリをインストール中...
pip install -r requirements.txt -q

echo [2/2] Activity Tracker を起動中...
start "" pythonw tracker.py

echo.
echo タスクトレイにアイコンが表示されます。
echo ダッシュボードはアイコン右クリック → "ダッシュボードを開く" から起動できます。
echo.
pause
