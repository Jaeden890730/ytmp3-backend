# Railway 重新部署與 YouTube cookies 設定

## 這次修改了什麼

- `app.py` 新增 `YTDLP_COOKIES_BASE64` / `YTDLP_COOKIES` / `YTDLP_COOKIES_FILE` 支援。
- Railway 上無法使用 `--cookies-from-browser`，所以改成從 Railway Variables 寫入 cookies.txt 給 yt-dlp 使用。
- `requirements.txt` 將 `yt-dlp` 更新到 `2026.6.9`。

## Railway 環境變數

建議使用：

```text
YTDLP_COOKIES_BASE64=你的 cookies.txt base64 字串
```

## Windows 產生 base64

PowerShell：

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\Users\你的使用者\Downloads\cookies.txt")) | Set-Clipboard
```

執行後會把 base64 字串複製到剪貼簿。

## macOS / Linux 產生 base64

```bash
base64 -w 0 cookies.txt
```

如果 macOS 沒有 `-w`：

```bash
base64 cookies.txt | tr -d '\n'
```

## Railway 設定方式

1. 進 Railway 專案。
2. 點你的後端 Service。
3. 到 `Variables`。
4. 新增：
   - Name：`YTDLP_COOKIES_BASE64`
   - Value：貼上 base64 字串
5. 儲存後 Railway 通常會自動重新部署。
6. 如果沒有自動部署，到 `Deployments` 點 `Redeploy`。

## GitHub 重新部署流程

```bash
git add app.py requirements.txt RAILWAY_DEPLOY.md
git commit -m "fix: add yt-dlp cookies support for Railway"
git push origin main
```

Railway 連接 GitHub 的話，push 後會自動觸發部署。

## 重要提醒

- 不要把 `cookies.txt` 或 base64 cookies commit 到 GitHub。
- cookies 可能會過期，如果之後又出現 bot / login 錯誤，需要重新匯出 cookies 並更新 Railway Variable。
- 請只下載自己擁有權限或符合平台規範的內容。
