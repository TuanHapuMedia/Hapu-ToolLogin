"""
Auto Login Tool - Tự động đăng nhập Google Account vào GPM-Login profile
Nhập Gmail | Password | Recovery Email → tool tự mở GPM profile và đăng nhập

Dùng: python auto_login_tool.py
"""
import asyncio
import logging
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, scrolledtext, ttk

import os
from pathlib import Path

import requests
from playwright.async_api import async_playwright

# ──────────────────────────────────────────────────────────
GPM_BASE = "http://127.0.0.1:19995"
GOOGLE_LOGIN = "https://accounts.google.com/signin/v2/identifier?hl=vi"
# Trang "Xác minh 2 bước" — trang FULL có nút Authenticator / Bật 2 bước
TWOSV_URL = "https://myaccount.google.com/signinoptions/twosv?hl=vi"

# Nút "Đổi/Thiết lập ứng dụng xác thực" — ĐA NGÔN NGỮ. Google hiển thị theo NGÔN NGỮ CỦA
# ACCOUNT (?hl= KHÔNG override account đã đăng nhập), nên phải liệt kê nhiều thứ tiếng.
# Cụm ĐẦY ĐỦ để trước; verb ngắn (Thay đổi/Change/更改…) để sau làm fallback — an toàn vì
# nút XOÁ dùng verb khác (Xoá/Delete/删除…).
_CHANGE_AUTH_TXT = [
    "Thay đổi ứng dụng xác thực", "Thiết lập ứng dụng xác thực",
    "Change authenticator app", "Change authenticator", "Set up authenticator",
    "更改身份验证器应用", "更改验证器应用", "设置身份验证器",
    "更改身份驗證器應用程式", "變更驗證器應用程式", "設定驗證器應用程式",
    "인증 앱 변경", "인증 앱 설정", "認証システムアプリの変更", "認証アプリを変更",
    "เปลี่ยนแอปตรวจสอบสิทธิ์", "ตั้งค่าแอปตรวจสอบสิทธิ์",
    "Cambiar la aplicación Authenticator", "Alterar app Authenticator",
    "Modifier l'application Authenticator", "Authenticator-App ändern",
    "Ubah aplikasi Authenticator", "Tukar apl Authenticator",
    "Изменить приложение Authenticator", "تغيير تطبيق المصادقة",
    "प्रमाणीकरण ऐप्लिकेशन बदलें", "Kimlik Doğrulayıcı uygulamasını değiştir",
    "Cambia app Authenticator",
    "Thay đổi", "Change", "更改", "變更", "변경", "変更", "เปลี่ยน", "Cambiar",
    "Alterar", "Mudar", "Modifier", "Ändern", "Ubah", "Tukar", "Изменить",
    "تغيير", "बदलें", "Değiştir", "Cambia",
]
# Mục "Authenticator" (Ứng dụng xác thực) trong danh sách 2 bước — đa ngôn ngữ.
_AUTH_ITEM_TXT = ["Authenticator", "Ứng dụng xác thực", "身份验证器", "身份驗證器",
                  "验证器", "驗證器", "認証システム", "認証アプリ", "인증", "Authentifizierung",
                  "Autenticador", "Authentificateur", "ตัวตรวจสอบสิทธิ์"]
# Nút "Tiếp theo / Continue" (dialog thiết lập 2FA) — đa ngôn ngữ.
_NEXT_TXT = ["Tiếp theo", "Next", "Continue", "आगे बढ़ें", "जारी रखें",
             "下一步", "继续", "繼續", "下一頁", "下一页", "下一項", "다음", "계속", "次へ", "続行",
             "ถัดไป", "ต่อไป", "Siguiente", "Continuar", "Suivant", "Weiter",
             "Berikutnya", "Lanjutkan", "Seterusnya", "Далее", "Продолжить",
             "التالي", "متابعة", "İleri", "Devam", "Avanti", "Continua"]
# Nút "Xác minh / Verify" — đa ngôn ngữ.
_VERIFY_TXT = ["Xác minh", "Verify", "पुष्टि करें", "सत्यापित करें",
               "验证", "驗證", "확인", "인증", "確認", "認証", "ยืนยัน",
               "Verificar", "Vérifier", "Bestätigen", "Verifikasi", "Sahkan",
               "Подтвердить", "Проверить", "تحقّق", "تأكيد", "Doğrula", "Verifica"]
# Nút HUỶ / QUAY LẠI — đa ngôn ngữ. TUYỆT ĐỐI KHÔNG bấm nhầm khi xác nhận 2FA
# (bấm Huỷ = đổi 2FA bị bỏ, nhưng tool tưởng xong → lưu secret sai → mất account).
_CANCEL_KW = ("cancel", "hủy", "huỷ", "quay lại", "trở lại", "batal", "kembali", "back",
              "取消", "返回", "上一步", "取消操作", "이전", "취소", "뒤로", "戻る", "キャンセル",
              "ยกเลิก", "กลับ", "abbrechen", "zurück", "cancelar", "volver", "atrás",
              "annuler", "retour", "отмена", "назад", "إلغاء", "رجوع", "السابق",
              "iptal", "geri", "annulla", "indietro")
# Thư mục chứa file này — dùng cho mọi ảnh/debug (tránh hardcode path sai máy)
_DIR = Path(__file__).resolve().parent


def _dbg_path(name: str) -> str:
    """Đường dẫn file debug/screenshot nằm cùng thư mục script."""
    return str(_DIR / name)
# ──────────────────────────────────────────────────────────


# ── GPM helpers ────────────────────────────────────────────
def gpm_list():
    r = requests.get(f"{GPM_BASE}/v2/profiles", timeout=10)
    r.raise_for_status()
    d = r.json()
    return d.get("data", d) if isinstance(d, dict) else d


def _get_ws_url(debug_addr: str) -> str:
    """Lấy WebSocket URL từ Chrome DevTools Protocol debug address."""
    import time as _time
    for attempt in range(5):
        try:
            _time.sleep(1.5)
            r = requests.get(f"http://{debug_addr}/json/version", timeout=5)
            if r.status_code == 200:
                info = r.json()
                ws = info.get("webSocketDebuggerUrl", "")
                if ws:
                    return ws
            r2 = requests.get(f"http://{debug_addr}/json", timeout=5)
            pages = r2.json()
            if pages:
                return pages[0].get("webSocketDebuggerUrl", f"ws://{debug_addr}")
        except Exception:
            pass
    return f"ws://{debug_addr}"


def gpm_start(pid):
    r = requests.get(f"{GPM_BASE}/v2/start", params={"profile_id": pid}, timeout=60)
    r.raise_for_status()
    d = r.json()
    if not d.get("status", False):
        raise RuntimeError(f"GPM start thất bại: {d}")
    # V2 trả về selenium_remote_debug_address thay vì wsUrl
    debug_addr = (
        d.get("selenium_remote_debug_address")
        or d.get("remote_debug_address")
        or d.get("wsUrl")
    )
    if not debug_addr:
        raise RuntimeError(f"Không lấy được debug address: {d}")
    if debug_addr.startswith("ws://") or debug_addr.startswith("http://"):
        return debug_addr.replace("http://", "ws://")
    return _get_ws_url(debug_addr)


def gpm_stop(pid):
    try:
        requests.get(f"{GPM_BASE}/v2/stop", params={"profile_id": pid}, timeout=20)
    except Exception:
        pass


def gpm_create(name: str) -> str:
    """Tạo profile mới — GPM V2 API không hỗ trợ create, raise RuntimeError để caller dùng gpm_client."""
    raise RuntimeError(
        "GPM API không hỗ trợ tạo profile — dùng GPMClient.create_profile() trong upload_gui.py"
    )


# ── Playwright login ────────────────────────────────────────
async def _handle_consent_page(page, log_fn):
    """Xử lý trang cookie consent của Google nếu xuất hiện."""
    url = page.url
    if "consent.google.com" in url or "consent" in url:
        log_fn("  ⚠ Phát hiện trang consent Google, đang xử lý...")
        # Thử click các nút "Accept"/"Reject" để qua consent
        for sel in [
            'button[id="L2AGLb"]',                    # Accept all (ID cũ)
            'button:has-text("Accept all")',
            'button:has-text("Chấp nhận tất cả")',
            'button:has-text("Reject all")',
            'button:has-text("Từ chối tất cả")',
            'button:has-text("I agree")',
            'button:has-text("Tôi đồng ý")',
            '[aria-label="Accept all"]',
        ]:
            try:
                btn = page.locator(sel)
                if await btn.count() > 0:
                    await btn.first.click()
                    log_fn(f"  ✓ Đã click consent: {sel[:40]}")
                    await page.wait_for_timeout(2000)
                    return True
            except Exception:
                pass
        log_fn("  ⚠ Không tìm thấy nút consent, tiếp tục thử...")
    return False


import re as _re

async def _capture_yt_handle(page, log_fn) -> str | None:
    """(TẮT) Chỉ cần đăng nhập Gmail, không vào YouTube Studio lấy link kênh."""
    return None


async def _capture_yt_handle_DISABLED(page, log_fn) -> str | None:
    try:
        log_fn("  📺 Mở YouTube Studio lấy link kênh...")
        await page.goto("https://studio.youtube.com",
                        wait_until="domcontentloaded", timeout=30000)
        # Studio tự redirect về /channel/UCxxxx
        try:
            await page.wait_for_url(lambda url: '/channel/UC' in url, timeout=15000)
        except Exception:
            pass  # timeout - kiểm tra URL bên dưới
        await page.wait_for_timeout(2000)
        cur = page.url
        log_fn(f"  🔎 Studio URL: {cur[:80]}")
        m = _re.search(r'/channel/(UC[0-9A-Za-z_-]{10,})', cur)
        if not m:
            # Studio load chậm qua proxy - đợi thêm
            await page.wait_for_timeout(6000)
            cur = page.url
            m = _re.search(r'/channel/(UC[0-9A-Za-z_-]{10,})', cur)
        if not m:
            try:
                _title = await page.title()
            except Exception:
                _title = "?"
            log_fn(f"  ⚠ Không thấy channel ID (url={cur[:60]}, title='{_title[:40]}')"
                   " — kênh có thể chưa tạo")
            return None
        cid = m.group(1)
        channel_url = f"https://www.youtube.com/channel/{cid}"
        # Thử nâng cấp sang link @handle đẹp hơn (nếu kênh có handle)
        try:
            await page.goto(channel_url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(2000)
            canon = await page.locator('link[rel="canonical"]').first.get_attribute('href') or ''
            m2 = _re.search(r'youtube\.com/(@[^/?&#]+)', canon)
            if m2 and m2.group(1).lower() != "@me":
                channel_url = f"https://www.youtube.com/{m2.group(1)}"
        except Exception:
            pass  # giữ link /channel/UCxxx
        log_fn(f"  📺 Link kênh: {channel_url}")
        return channel_url
    except Exception as e:
        log_fn(f"  ⚠ Lấy link kênh lỗi: {e}")
    return None


import base64 as _b64
import hashlib as _hashlib
import hmac as _hmac
import struct as _struct
import time as _time_totp

# ── ĐỒNG BỘ GIỜ (quan trọng cho TOTP) ─────────────────────────────
# TOTP phụ thuộc GIỜ UTC. Nếu ĐỒNG HỒ MÁY sai (sai timezone / lệch phút) thì mã sinh ra
# lệch → Google TỪ CHỐI ("sai mã") dù secret ĐÚNG. Đây từng là lỗi máy lệch +7 giờ (lấy giờ
# VN coi như UTC). Giống Google Authenticator "time correction", ta lấy GIỜ THẬT từ header
# 'Date' của server Google, tính độ lệch so với đồng hồ máy, rồi BÙ vào mọi mã TOTP.
_TIME_OFFSET = 0.0        # giây: (giờ thật server) − (giờ máy)
_TIME_SYNCED = False
_TIME_LOCK = threading.Lock()


def sync_time_offset(log_fn=None):
    """Lấy giờ thật từ server Google → cập nhật _TIME_OFFSET. Gọi 1 lần lúc bắt đầu chạy."""
    global _TIME_OFFSET, _TIME_SYNCED
    with _TIME_LOCK:
        try:
            import email.utils as _eut
            for _url in ("https://accounts.google.com/generate_204",
                         "https://www.google.com/generate_204",
                         "https://www.google.com"):
                try:
                    r = requests.head(_url, timeout=4, allow_redirects=False)
                    d = r.headers.get("Date")
                    if d:
                        srv = _eut.parsedate_to_datetime(d).timestamp()
                        _TIME_OFFSET = srv - _time_totp.time()
                        _TIME_SYNCED = True
                        if log_fn:
                            log_fn(f"  [GIỜ] Đồng bộ giờ server OK — đồng hồ máy lệch "
                                   f"{_TIME_OFFSET:+.0f}s (đã bù cho TOTP).")
                        return _TIME_OFFSET
                except Exception:
                    pass
        except Exception:
            pass
        _TIME_SYNCED = True   # đánh dấu đã thử (khỏi thử lại liên tục), dùng giờ máy nếu fail
        if log_fn:
            log_fn("  [GIỜ] ⚠ Không lấy được giờ server — dùng giờ máy (nếu máy sai giờ, "
                   "TOTP có thể bị từ chối; hãy chỉnh đồng hồ Windows tự đồng bộ).")
    return _TIME_OFFSET


def _ensure_time_synced():
    if not _TIME_SYNCED:
        sync_time_offset()


def totp_now(secret: str, digits: int = 6, period: int = 30) -> str:
    """Sinh mã TOTP 6 số từ secret base32 (giống Google Authenticator / 2fa.live).
    Dùng GIỜ ĐÃ BÙ (_TIME_OFFSET) để không lệ thuộc đồng hồ máy có thể sai."""
    _ensure_time_synced()
    s = (secret or "").replace(" ", "").replace("-", "").upper()
    pad = "=" * ((8 - len(s) % 8) % 8)
    key = _b64.b32decode(s + pad, casefold=True)
    counter = int(_time_totp.time() + _TIME_OFFSET) // period
    msg = _struct.pack(">Q", counter)
    h = _hmac.new(key, msg, _hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (_struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def _valid_b32_secret(s: str) -> bool:
    """
    True nếu chuỗi là TOTP secret base32 HỢP LỆ.
    Chống nhận nhầm chữ tiếng Anh trong HTML (vd 'CONNECTEDACCOUNTS'):
      - Chỉ ký tự A-Z2-7
      - Độ dài >= 16 và chia hết cho 8 (block base32 chuẩn — secret Google là 32)
      - Giải mã base32 thành công
    """
    import re as __re
    s = (s or "").replace(" ", "").replace("-", "").upper()
    if len(s) < 16 or len(s) % 8 != 0:
        return False
    if not __re.fullmatch(r"[A-Z2-7]+", s):
        return False
    # Chống giá trị RÁC lặp lại (vd '24PX24PX…' bắt nhầm từ CSS 'padding:24px 24px …'):
    # secret Google thật rất đa dạng ký tự, KHÔNG phải 1 khối lặp đi lặp lại.
    if len(set(s)) < 6:
        return False
    for _blk in (2, 4, 8):
        if len(s) % _blk == 0 and len({s[i:i + _blk] for i in range(0, len(s), _blk)}) == 1:
            return False
    try:
        _b64.b32decode(s, casefold=True)
        return True
    except Exception:
        return False


async def _try_totp(page, secret: str, log_fn) -> bool:
    """Tìm ô nhập mã 2FA (authenticator) và điền mã sinh từ secret. Trả True nếu đã nhập."""
    if not secret:
        return False
    # Nếu Google đang hỏi 'Try another way' / chọn phương thức, thử chọn Authenticator
    for txt in ["Google Authenticator", "authenticator", "Xác minh bằng ứng dụng",
                "Nhận mã xác minh từ ứng dụng"]:
        try:
            opt = page.locator(f"text={txt}")
            if await opt.count() > 0 and await opt.first.is_visible():
                await opt.first.click()
                await page.wait_for_timeout(2000)
                break
        except Exception:
            pass
    sels = ['input[name="totpPin"]', 'input#totpPin',
            'input[autocomplete="one-time-code"]', 'input[type="tel"]']
    inp = None
    for s in sels:
        try:
            loc = page.locator(s)
            if await loc.count() > 0 and await loc.first.is_visible():
                inp = loc.first
                break
        except Exception:
            pass
    if inp is None:
        return False
    # Dùng totp_now cục bộ trực tiếp (bỏ 2fa.live để tránh code sai/chậm)
    try:
        code = totp_now(secret)
        log_fn(f"  🔑 Nhập mã 2FA: {code}")
    except Exception as e:
        log_fn(f"  ✗ 2FA secret không hợp lệ: {e}")
        return False
    await inp.click()
    # XÓA SẠCH ô trước khi gõ — tránh nối chuỗi mã (vd 476654+896034+... = 18 số → sai)
    try:
        await inp.fill("")
    except Exception:
        try:
            await inp.press("Control+a")
            await inp.press("Delete")
        except Exception:
            pass
    await inp.type(code, delay=90)   # gõ hiện chữ
    await _click_next(page, "#totpNext")
    await page.wait_for_timeout(3500)
    return True


async def _get_2fa_via_live(ctx, secret: str, log_fn) -> str:
    """Mở tab https://2fa.live, dán secret, lấy mã 6 số. Trả '' nếu lỗi."""
    tab = None
    try:
        log_fn("  🌐 Mở tab 2fa.live lấy mã 2FA...")
        tab = await ctx.new_page()
        await tab.goto("https://2fa.live/", wait_until="domcontentloaded", timeout=30000)
        await tab.wait_for_timeout(1500)
        # Ô nhập secret
        inp = tab.locator('#listToken, textarea, input[type="text"]').first
        await inp.click()
        await inp.fill(secret)
        await tab.wait_for_timeout(500)
        # Bấm nút tạo mã
        for sel in ['button:has-text("Submit")', 'button:has-text("Generate")',
                    'button:has-text("Get")', '#submit', 'button[type="submit"]', 'button']:
            try:
                b = tab.locator(sel)
                if await b.count() > 0 and await b.first.is_visible():
                    await b.first.click()
                    break
            except Exception:
                pass
        await tab.wait_for_timeout(2000)
        # Đọc mã 6 số trên trang
        import re
        body = await tab.inner_text("body")
        m = re.search(r'(?<!\d)(\d{6})(?!\d)', body)
        if m:
            log_fn(f"  ✓ 2fa.live trả mã: {m.group(1)}")
            return m.group(1)
        log_fn("  ⚠ Không đọc được mã từ 2fa.live")
    except Exception as e:
        log_fn(f"  ⚠ 2fa.live lỗi: {str(e)[:50]}")
    finally:
        if tab:
            try:
                await tab.wait_for_timeout(800)
                await tab.close()
            except Exception:
                pass
    return ""


async def _click_next(page, prefer_id: str = "") -> bool:
    """Bấm nút Next/Đăng nhập (ưu tiên id), fallback submit form qua JS.
    KHÔNG dùng keyboard để tránh crash Chromium 119."""
    sels = []
    if prefer_id:
        sels += [f'{prefer_id} button', prefer_id]
    sels += [f'button:has-text("{t}")' for t in _NEXT_TXT]
    sels += ['button:has-text("Đăng nhập")', '#identifierNext', '#passwordNext']
    for sel in sels:
        try:
            b = page.locator(sel)
            if await b.count() > 0 and await b.first.is_visible():
                await b.first.click()
                return True
        except Exception:
            pass
    try:
        await page.evaluate("""() => {
            const btn = document.querySelector('#identifierNext, #passwordNext, button[jsname], [type=submit]');
            if (btn) { btn.click(); return; }
            const el = document.activeElement;
            const f = el && el.form; if (f) { f.requestSubmit ? f.requestSubmit() : f.submit(); }
        }""")
        return True
    except Exception:
        return False


async def _read_error_text(page) -> str:
    """Đọc thông báo lỗi Google (sai mật khẩu / sai email...) nếu có."""
    for sel in ['[aria-live="assertive"]', 'div[jsname="B34EJ"]',
                '.o6cuMc', '.OyEIQ', '.dEOOab', '.Ekjuhf']:
        try:
            loc = page.locator(sel)
            n = await loc.count()
            for i in range(n):
                t = (await loc.nth(i).text_content() or "").strip()
                if t:
                    return t
        except Exception:
            pass
    return ""


async def _dismiss_post_login_prompts(page, log_fn, max_rounds: int = 5):
    """
    Bỏ qua các popup Google xuất hiện sau khi đăng nhập:
    - 'Đảm bảo rằng bạn luôn có thể đăng nhập' → Huỷ
    - 'Đặt địa chỉ nhà riêng' → Bỏ qua
    - Các popup khác với nút Bỏ qua / Huỷ / Skip / Not now
    """
    # Đa ngôn ngữ (VN + EN) — Google có thể hiển thị tiếng Anh trên 1 số account
    skip_texts = [
        "Bỏ qua", "Huỷ", "Hủy", "Để sau", "Nhắc tôi sau", "Không, cảm ơn",
        "Skip", "Not now", "Later", "Remind me later", "No thanks",
        "Cancel", "Dismiss", "Maybe later",
        # Popup 'Liên kết với các dịch vụ của Google?' → chọn hoãn (KHÔNG bấm 'Bắt đầu')
        "Hỏi tôi sau 3 ngày nữa", "Hỏi tôi sau", "Hỏi lại sau", "Ask me in 3 days",
        "Ask again later", "Ask me later", "Remind me in 3 days",
    ]
    for _ in range(max_rounds):
        await page.wait_for_timeout(1500)
        found = False
        try:
            frames = list(page.frames)
        except Exception:
            frames = [page]
        for fr in frames:
            for txt in skip_texts:
                try:
                    for tag in ["button", "a", "span", "div", "[role='button']"]:
                        sel = f'{tag}:has-text("{txt}")'
                        el = fr.locator(sel)
                        cnt = await el.count()
                        for i in range(min(cnt, 4)):
                            try:
                                item = el.nth(i)
                                if await item.is_visible():
                                    bb = await item.bounding_box()
                                    if bb and bb["width"] < 320:  # nút nhỏ, không phải link lớn
                                        if await _click_el(item, 4000):
                                            log_fn(f"  ✓ Bỏ qua popup: '{txt}'")
                                            await page.wait_for_timeout(1200)
                                            found = True
                                            break
                            except Exception:
                                pass
                        if found:
                            break
                except Exception:
                    pass
                if found:
                    break
            if found:
                break
        if not found:
            break  # Không còn popup nào


def _is_logged_in(url: str) -> bool:
    """Kiểm tra URL hiện tại là trang Google đã đăng nhập (không phải trang xác thực)."""
    if not url:
        return False
    # BỎ phần query (?...) trước khi kiểm tra: trang gds có 'continue=...accounts.google.com...'
    # trong query -> nếu không bỏ sẽ tưởng nhầm là trang accounts (chưa đăng nhập).
    url = url.split("?", 1)[0]
    # Còn trên trang xác thực / đăng nhập → chưa đăng nhập
    if any(s in url for s in ["accounts.google.com", "consent.google.com"]):
        return False
    # Trang Google bình thường sau đăng nhập (kể cả các trang nudge gds.google.com
    # như 'địa chỉ nhà riêng', 'video-verification'… — tới được nghĩa là ĐÃ đăng nhập)
    return any(s in url for s in [
        "myaccount.google.com",
        "mail.google.com",
        "google.com/gmail",
        "google.com/u/",
        "studio.youtube.com",
        "youtube.com/channel",
        "gds.google.com",
        "google.com/webhp",
    ])


async def do_google_login(ws_url: str, email: str, password: str, recovery: str,
                          totp_secret: str = "", log_fn=print):

    async with async_playwright() as p:
        log_fn("  Kết nối browser GPM...")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()

        # ── FAST CHECK: nếu profile đã login thì thoát sớm ──────────────
        try:
            await page.goto("https://myaccount.google.com/",
                            wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1500)
            _fc_url = page.url
            if ("myaccount.google.com" in _fc_url
                    and "signin" not in _fc_url
                    and "challenge" not in _fc_url):
                log_fn("  ✅ Profile đã đăng nhập sẵn – bỏ qua bước login!")
                ch = await _capture_yt_handle(page, log_fn)
                await page.close()
                return True, "Đã đăng nhập sẵn", ch
        except Exception as _fc_e:
            log_fn(f"  [fast-check] {_fc_e}")

        # ── Vào gmail.com trước, rồi bấm "Đăng nhập" (giống người dùng) ──
        await _skip_selfie_video(page, log_fn)
        log_fn("  Mở gmail.com...")
        try:
            await page.goto("https://www.google.com/gmail/about/",
                            wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)
            # Bấm nút "Đăng nhập" / "Sign in" trên trang gmail
            clicked_signin = False
            for sel in ['a:has-text("Đăng nhập")', 'a:has-text("Sign in")',
                        'a[href*="ServiceLogin"]', 'a[data-action="sign in"]',
                        'a[href*="accounts.google.com"]']:
                try:
                    b = page.locator(sel)
                    if await b.count() > 0 and await b.first.is_visible():
                        await b.first.click()
                        clicked_signin = True
                        log_fn("  ✓ Đã bấm 'Đăng nhập'")
                        break
                except Exception:
                    pass
            await page.wait_for_timeout(3000)
            # Nếu chưa tới trang đăng nhập -> vào thẳng trang login
            if "accounts.google.com" not in page.url:
                await page.goto(GOOGLE_LOGIN, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(2500)
        except Exception as e:
            log_fn(f"  ⚠ Vào gmail lỗi ({str(e)[:40]}), vào thẳng trang login...")
            await page.goto(GOOGLE_LOGIN, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)

        cur = page.url
        log_fn(f"  URL ban đầu: {cur[:70]}")

        # ── Xử lý consent page ─────────────────────────────────
        await _handle_consent_page(page, log_fn)
        # Nếu consent redirect về trang khác, navigate lại về login
        if "consent.google.com" not in page.url and "identifier" not in page.url and "ServiceLogin" not in page.url:
            pass  # đã xử lý consent, trang hiện tại là login
        if "consent.google.com" in page.url:
            # Consent chưa xử lý xong, navigate thẳng đến login
            log_fn("  Điều hướng lại về trang đăng nhập...")
            await page.goto(GOOGLE_LOGIN, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)

        cur = page.url
        log_fn(f"  URL sau consent: {cur[:70]}")

        # ── Đã đăng nhập rồi? ──────────────────────────────────
        if _is_logged_in(cur):
            log_fn("  ✅ Tài khoản đã đăng nhập sẵn!")
            ch = await _capture_yt_handle(page, log_fn)
            await page.close()
            return True, "Đã đăng nhập sẵn", ch

        # ── Trang "Chọn tài khoản" ─────────────────────────────
        if "ServiceLogin" in cur or "identifier" in cur or "AccountChooser" in cur:
            already_card = page.locator(f'[data-identifier="{email}"]')
            if await already_card.count() > 0:
                log_fn("  Tài khoản đã có trong danh sách, click chọn...")
                await already_card.first.click()
                await page.wait_for_timeout(3000)
                if _is_logged_in(page.url):
                    ch = await _capture_yt_handle(page, log_fn)
                    await page.close()
                    return True, page.url, ch
            # Click "Dùng tài khoản khác"
            for txt in ["Use another account", "Dùng tài khoản khác", "Add account"]:
                btn = page.locator(f"text={txt}")
                if await btn.count() > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(2000)
                    break

        # ── Nhập email ─────────────────────────────────────────
        log_fn("  Nhập email...")
        # Nhiều selector cho email input (Google thay đổi theo version)
        email_input = page.locator(
            'input[type="email"], '
            'input[name="identifier"], '
            'input[autocomplete="username"]'
        )
        try:
            await email_input.first.wait_for(timeout=15000, state="visible")
        except Exception:
            # Debug: log thông tin trang để hiểu lỗi
            try:
                title = await page.title()
                url_now = page.url
                log_fn(f"  ⚠ Debug: title='{title[:50]}', url={url_now[:80]}")
            except Exception:
                pass
            await page.close()
            return False, "Không tìm thấy ô nhập email", None
        # Đưa cửa sổ browser lên trước để thấy gõ chữ
        try:
            await page.bring_to_front()
        except Exception:
            pass
        await email_input.first.click()
        await page.wait_for_timeout(500)
        # Kiểm tra xem ô đã có email chưa — nếu đúng thì không gõ lại (tránh doubled)
        existing_val = ""
        try:
            existing_val = await email_input.first.input_value()
        except Exception:
            pass
        if existing_val.strip().lower() == email.strip().lower():
            log_fn(f"  → Email đã có sẵn trong ô, bỏ qua gõ: {email}")
        else:
            # Clear field trước (select all + delete) để tránh append vào giá trị cũ
            try:
                await email_input.first.triple_click()
                await page.wait_for_timeout(150)
                await email_input.first.press("Control+a")
                await page.wait_for_timeout(150)
                await email_input.first.press("Delete")
                await page.wait_for_timeout(150)
            except Exception:
                pass
            log_fn(f"  → Đang gõ email: {email}")
            await email_input.first.type(email, delay=150)   # 150ms/ký tự — thấy rõ từng chữ
        typed_val = ""
        try:
            typed_val = await email_input.first.input_value()
        except Exception:
            pass
        log_fn(f"  ✓ Đã gõ email (ô hiện: '{typed_val[:40]}')")
        await page.wait_for_timeout(600)
        # Bấm nút "Tiếp theo / Next" (không dùng keyboard để tránh crash)
        await _click_next(page, "#identifierNext")
        await page.wait_for_timeout(3000)
        log_fn(f"  URL sau email: {page.url[:75]}")

        # ── /signin/rejected: có thể là 'Đã vô hiệu hóa tài khoản' (disabled) HOẶC block IP ─
        if "/signin/rejected" in page.url or "signin/rejected" in page.url.lower():
            try:
                _rb = (await page.inner_text("body"))[:2500].lower()
            except Exception:
                _rb = ""
            if any(k in _rb for k in [
                    "vô hiệu hóa tài khoản", "vô hiệu hoá tài khoản",
                    "đã vô hiệu hóa", "đã vô hiệu hoá", "disabled",
                    "đã khóa tài khoản", "đã khoá tài khoản",
                    "hoạt động bất thường"]):
                log_fn("  ✗ Tài khoản bị VÔ HIỆU HOÁ (trang 'Đã vô hiệu hóa tài khoản')")
                await page.close()
                return False, "DISABLED | Tài khoản Gmail đã bị vô hiệu hoá", None
            log_fn(f"  ⚠ /signin/rejected — Google từ chối đăng nhập (IP hoặc tài khoản bị chặn)")
            await page.close()
            return False, "GOOGLE_BLOCKED | Google từ chối ngay sau email — IP hoặc tài khoản bị chặn (/signin/rejected)", None

        # ── Detect CAPTCHA / xác minh danh tính sau bước email ─
        _url_after_email = page.url.lower()
        # Detect qua URL (nhanh nhất — không cần đọc DOM)
        _captcha_by_url = (
            "recaptcha" in _url_after_email
            or ("/challenge/" in _url_after_email and "recaptcha" in _url_after_email)
        )
        # Detect qua nội dung body
        try:
            _body_chk = (await page.inner_text("body"))[:3000].lower()
        except Exception:
            _body_chk = ""
        _captcha_kw = [
            "không phải là người máy", "i'm not a robot", "not a robot",
            "xác minh danh tính", "verify it's you", "verify your identity",
            "xác nhận bạn không phải", "recaptcha",
        ]
        _captcha_in_body = any(k in _body_chk for k in _captcha_kw)
        # Detect qua frame URLs
        _captcha_in_frame = False
        try:
            for _fr in page.frames:
                if "recaptcha" in (_fr.url or "").lower() or "hcaptcha" in (_fr.url or "").lower():
                    _captcha_in_frame = True
                    break
        except Exception:
            pass
        if _captcha_by_url or _captcha_in_body or _captcha_in_frame:
            log_fn(f"  ⚠ CAPTCHA phát hiện (url={page.url[40:80]})")
            await page.close()
            return False, "CAPTCHA | Google yêu cầu xác minh CAPTCHA — cần đổi proxy hoặc chờ", None

        # ── Nhập password ──────────────────────────────────────
        log_fn("  Nhập mật khẩu...")
        pass_input = page.locator(
            'input[type="password"], input[name="Passwd"], '
            'input[autocomplete="current-password"]'
        )
        try:
            # Chờ lâu hơn vì trang v3 + proxy có thể chậm chuyển bước
            await pass_input.first.wait_for(timeout=25000, state="visible")
        except Exception:
            # Không thấy ô mật khẩu -> CHỤP LẠI trang + đọc error/body để biết Google báo gì
            try:
                await page.screenshot(path=_dbg_path("debug_no_password.png"), timeout=5000)
            except Exception:
                pass
            emsg = await _read_error_text(page)
            try:
                body_low = (await page.inner_text("body"))[:2500].lower()
            except Exception:
                body_low = ""
            low = (emsg + " " + body_low).lower()
            _url = page.url
            log_fn(f"  ⚠ Debug: url={_url[:80]}, msg='{emsg[:60]}'")
            await page.close()
            # Google chặn: quá nhiều lần thử
            if any(k in low for k in ["too many failed", "too many attempts",
                                      "quá nhiều lần", "try again later",
                                      "thử lại sau", "unusual traffic",
                                      "次数过多", "尝试次数过多", "請稍後再試", "稍后再试"]):
                return False, f"TOO_MANY_ATTEMPTS | Google chặn quá nhiều lần thử — {emsg[:90]}", None
            # Trình duyệt không an toàn (Google chặn automation)
            if any(k in low for k in ["not secure", "browser or app may not be secure",
                                      "không an toàn", "trình duyệt hoặc ứng dụng",
                                      "浏览器或应用", "瀏覽器或應用程式", "可能不安全"]):
                return False, f"BROWSER_NOT_SECURE | Google chặn: trình duyệt không an toàn — {emsg[:80]}", None
            # Tài khoản bị vô hiệu hoá
            if any(k in low for k in ["disabled", "bị vô hiệu", "đã bị vô hiệu",
                                      "account has been disabled", "已停用", "已被停用"]):
                return False, f"DISABLED | Tài khoản bị vô hiệu hoá — {emsg[:80]}", None
            # Sai email / không tồn tại
            if any(k in low for k in ["couldn't find", "can't find", "not find",
                                      "không tìm thấy tài khoản", "doesn't exist",
                                      "không tồn tại", "no account found",
                                      "找不到", "找不到您的 google", "找不到您的"]):
                return False, f"SAI_EMAIL | {emsg[:120]}", None
            # Google bắt XÁC MINH ngay trước bước mật khẩu (verify it's you / challenge)
            if ("challenge" in _url.lower()) or any(k in low for k in [
                    "verify it's you", "xác minh danh tính", "xác minh", "verify your identity",
                    "confirm it's you", "确认您的身份", "验证您的身份", "確認是您本人",
                    "驗證您的身分", "본인 확인"]):
                return False, f"VERIFY | Google yêu cầu xác minh trước bước mật khẩu — {emsg[:80]}", None
            return False, f"KHÔNG TỚI ĐƯỢC BƯỚC MẬT KHẨU | {emsg[:120]}", None
        try:
            await page.bring_to_front()
        except Exception:
            pass
        await pass_input.first.click()
        await page.wait_for_timeout(400)
        log_fn(f"  → Đang gõ mật khẩu...")
        await pass_input.first.type(password, delay=100)   # 100ms/ký tự
        await page.wait_for_timeout(600)
        # Bấm nút mật khẩu (không dùng keyboard)
        await _click_next(page, "#passwordNext")
        await page.wait_for_timeout(5000)

        cur = page.url
        log_fn(f"  URL sau password: {cur[:70]}")

        # ── Phát hiện tài khoản bị vô hiệu hoá (disabled) ───────
        try:
            body_txt = (await page.inner_text("body"))[:2000].lower()
        except Exception:
            body_txt = ""
        if any(k in body_txt for k in [
                "account disabled", "has been disabled", "account has been disabled",
                "account is disabled", "bị tắt",
                # Trang "Đã vô hiệu hóa tài khoản" (KHÔNG có chữ 'bị')
                "vô hiệu hóa tài khoản", "vô hiệu hoá tài khoản",
                "đã vô hiệu hóa", "đã vô hiệu hoá",
                "tài khoản đã bị vô hiệu", "đã bị vô hiệu hoá", "đã bị vô hiệu hóa",
                "đã khóa tài khoản", "đã khoá tài khoản",
                "hoạt động bất thường trong tài khoản"]):
            log_fn("  ✗ Tài khoản Gmail bị VÔ HIỆU HOÁ (disabled)")
            await page.close()
            return False, "DISABLED | Tài khoản Gmail đã bị vô hiệu hoá", None

        # ── Phát hiện sai mật khẩu ──────────────────────────────
        if not _is_logged_in(cur) and "challenge" not in cur and "accounts.google.com" in cur:
            perr = await _read_error_text(page)
            plow = perr.lower()
            if any(k in plow for k in ["wrong password", "incorrect", "không đúng",
                                       "sai mật khẩu", "mật khẩu bạn đã nhập",
                                       "mật khẩu của bạn đã thay đổi", "mật khẩu đã thay đổi",
                                       "password was changed", "changed your password"]):
                log_fn(f"  ✗ Sai mật khẩu: {perr[:60]}")
                await page.close()
                return False, f"SAI_MATKHAU | {perr[:120]}", None

        # ── Challenge: 2FA (TOTP) → recovery email ──────────────
        if "challenge" in cur or "verify" in cur.lower():
            log_fn("  Phát hiện challenge...")

            # /challenge/pwd CŨNG CHÍNH LÀ trang nhập mật khẩu. Ở lại đây sau khi bấm
            # Next KHÔNG chắc là sai pass — có thể proxy chậm/trang chưa kịp chuyển tiếp.
            # → Chỉ kết luận SAI mật khẩu khi CÓ thông báo lỗi thật. Nếu không, chờ
            #   trang rời /challenge/pwd rồi tiếp tục flow challenge bình thường.
            if "/challenge/pwd" in page.url:
                # Trang báo "Mật khẩu của bạn đã thay đổi X trước" = mật khẩu ĐÃ ĐỔI → sai pass
                try:
                    _pwbody = (await page.inner_text("body"))[:2500].lower()
                except Exception:
                    _pwbody = ""
                if any(k in _pwbody for k in [
                        "mật khẩu của bạn đã thay đổi", "mật khẩu đã thay đổi",
                        "đã thay đổi mật khẩu", "password was changed",
                        "you changed your password", "changed your password"]):
                    log_fn("  ✗ Mật khẩu ĐÃ THAY ĐỔI → sai mật khẩu")
                    await page.close()
                    return False, "SAI_MK | Mật khẩu đã thay đổi (sai mật khẩu)", None
                # Chỉ những cụm RÕ RÀNG về mật khẩu — tránh báo nhầm khi lỗi tạm thời
                _PWD_ERR_KEYS = [
                    "wrong password", "incorrect password", "password was incorrect",
                    "your password was wrong", "mật khẩu bạn đã nhập không đúng",
                    "sai mật khẩu", "mật khẩu không chính xác", "mật khẩu không đúng",
                ]
                _left_pwd = False
                for _pi in range(12):   # chờ tối đa ~18s để rời trang pwd
                    _perr = await _read_error_text(page)
                    _pl = (_perr or "").lower()
                    if _perr and any(k in _pl for k in _PWD_ERR_KEYS):
                        log_fn(f"  ✗ Sai mật khẩu (có báo lỗi): {_perr[:70]}")
                        await page.close()
                        return False, f"SAI_MK | Mật khẩu sai/đã đổi — {_perr[:100]}", None
                    if "/challenge/pwd" not in page.url:
                        _left_pwd = True
                        break
                    if _pi == 2:   # phòng khi cú bấm Next đầu chưa ăn → bấm lại
                        try:
                            await _click_next(page, "#passwordNext")
                        except Exception:
                            pass
                    if _pi == 5:   # thử submit bằng Enter
                        try:
                            await pass_input.first.click()
                            await page.keyboard.press("Enter")
                        except Exception:
                            pass
                    await page.wait_for_timeout(1500)
                cur = page.url
                log_fn(f"  URL sau khi xử lý pwd: {cur[:70]}")
                if not _left_pwd and "/challenge/pwd" in page.url:
                    # Vẫn kẹt ở trang mật khẩu mà KHÔNG hề có báo sai pass → nghi proxy chậm
                    log_fn("  ⚠ Kẹt ở /challenge/pwd (không có báo sai pass) — có thể proxy chậm")
                    await page.close()
                    return False, "PWD_STUCK | Kẹt ở trang mật khẩu, không có thông báo sai pass (thử lại / đổi proxy)", None
                # Đã rời /challenge/pwd → rơi xuống xử lý challenge tiếp theo (TOTP/selection…)

            # Kiểm tra CAPTCHA ngay — không để rơi vào chờ 60 giây
            _ch_url_low = page.url.lower()
            if "recaptcha" in _ch_url_low or "hcaptcha" in _ch_url_low:
                log_fn(f"  ⚠ CAPTCHA sau password (url={page.url[40:80]})")
                await page.close()
                return False, "CAPTCHA | Google yêu cầu xác minh CAPTCHA sau password — cần đổi proxy", None
            try:
                _ch_body = (await page.inner_text("body"))[:2000].lower()
                if any(k in _ch_body for k in ["không phải là người máy", "not a robot", "recaptcha"]):
                    log_fn("  ⚠ CAPTCHA sau password (phát hiện qua body)")
                    await page.close()
                    return False, "CAPTCHA | Google yêu cầu xác minh CAPTCHA sau password — cần đổi proxy", None
            except Exception:
                pass

            # 0) Trang /challenge/selection: chọn "Xác nhận email khôi phục" (dòng 3)
            async def _select_recovery_option():
                """Bấm vào tuỳ chọn 'Xác nhận email khôi phục của bạn' trên trang selection."""
                if "selection" not in page.url and "challenge" not in page.url:
                    return False
                await page.wait_for_timeout(2000)
                # Ưu tiên: tìm text chính xác như Google hiển thị (tiếng Việt)
                for txt in [
                    "Xác nhận email khôi phục của bạn",
                    "Xác nhận email khôi phục",
                    "email khôi phục",
                    "Confirm your recovery email",
                    "recovery email",
                ]:
                    for tag in ["li", "div", "a", "span", "p"]:
                        sel = f'{tag}:has-text("{txt}")'
                        try:
                            el = page.locator(sel)
                            cnt = await el.count()
                            for i in range(min(cnt, 5)):
                                try:
                                    item = el.nth(i)
                                    if await item.is_visible():
                                        bb = await item.bounding_box()
                                        if bb and bb["width"] > 50:
                                            await item.click()
                                            log_fn(f"  ✓ Click '{txt[:30]}' ({tag})")
                                            await page.wait_for_timeout(2000)
                                            return True
                                except Exception:
                                    pass
                        except Exception:
                            pass
                # Fallback data-challengetype
                for sel in [
                    'div[data-challengetype="12"]',
                    'div[data-challengetype="KNOWLEDGE_PREREGISTERED_EMAIL"]',
                    '[data-email-obfuscation]',
                ]:
                    try:
                        el = page.locator(sel)
                        if await el.count() > 0 and await el.first.is_visible():
                            await el.first.click()
                            log_fn("  ✓ Chọn xác minh bằng email khôi phục (data attr)")
                            await page.wait_for_timeout(2000)
                            return True
                    except Exception:
                        pass
                log_fn("  ⚠ Không tìm thấy tùy chọn recovery email")
                # Log tat ca items tren trang de debug
                try:
                    _all_li = page.locator('li')
                    _li_cnt = await _all_li.count()
                    log_fn(f"  [debug] Co {_li_cnt} li items tren trang:")
                    for _i in range(min(_li_cnt, 10)):
                        try:
                            _t = (await _all_li.nth(_i).inner_text()).strip()[:60]
                            log_fn(f"    li[{_i}]: {_t!r}")
                        except Exception:
                            pass
                    # Screenshot de debug (dùng _dbg_path — đúng thư mục mọi máy, KHÔNG hardcode)
                    await page.screenshot(path=_dbg_path("debug_selection_page.png"), timeout=5000)
                    log_fn("  [debug] Screenshot: debug_selection_page.png")
                except Exception as _de:
                    log_fn(f"  [debug] error: {_de}")
                # Fallback: tìm "email" trong li, sau đó thử "Thử cách khác"
                for container_sel in [
                    'li', 'div[role="option"]', 'div[role="listitem"]',
                    '[role="listitem"]', 'ul li', 'ul[role="list"] li',
                ]:
                    try:
                        items = page.locator(container_sel)
                        cnt = await items.count()
                        if cnt >= 2:
                            # Ưu tiên item có chứa "email"
                            for i in range(cnt):
                                try:
                                    txt = (await items.nth(i).inner_text()).lower()
                                    if "email" in txt and await items.nth(i).is_visible():
                                        await items.nth(i).click()
                                        log_fn(f"  ✓ Click item có 'email': {txt[:40]}")
                                        await page.wait_for_timeout(2000)
                                        return True
                                except Exception:
                                    pass
                            # Tiếp theo: click "Thử cách khác" nếu có
                            for i in range(cnt):
                                try:
                                    item_txt = (await items.nth(i).inner_text()).strip()
                                    if item_txt in ["Thử cách khác", "Try another way", "More options"] and await items.nth(i).is_visible():
                                        await items.nth(i).click()
                                        log_fn(f"  ✓ Click 'Thử cách khác' từ selection page")
                                        await page.wait_for_timeout(3000)
                                        # Sau khi click Thử cách khác, thử tìm lại email option
                                        for txt2 in ["Xác nhận email khôi phục của bạn", "email khôi phục", "Confirm your recovery email", "recovery email"]:
                                            for tag2 in ["li", "div", "a", "span"]:
                                                try:
                                                    el2 = page.locator(f'{tag2}:has-text("{txt2}")')
                                                    if await el2.count() > 0 and await el2.first.is_visible():
                                                        bb2 = await el2.first.bounding_box()
                                                        if bb2 and bb2["width"] > 50:
                                                            await el2.first.click()
                                                            log_fn(f"  ✓ Click '{txt2[:30]}' sau Thử cách khác")
                                                            await page.wait_for_timeout(2000)
                                                            return True
                                                except Exception:
                                                    pass
                                        # Dù không tìm được email option, đã click Thử cách khác
                                        return True
                                except Exception:
                                    pass
                    except Exception:
                        pass
                log_fn("  ⚠ Không tìm thấy tùy chọn recovery email trong selection page")
                return False

            async def _enter_recovery_email():
                """Nhập recovery email vào ô input và xác nhận.
                Poll chờ ô input xuất hiện (trang recovery của Google load chậm sau
                khi click option → không thể tìm 1 lần rồi bỏ cuộc)."""
                if not recovery:
                    return False
                sels = [
                    'input[name="knowledgePreregisteredEmailResponse"]',
                    'input[type="email"]',
                    'input[aria-label*="email" i]',
                    'input[aria-label*="khôi phục" i]',
                    'input[placeholder*="khôi phục" i]',
                    'input[type="text"]',
                ]
                # Poll tối đa ~12s cho ô input xuất hiện
                for _poll in range(12):
                    for sel in sels:
                        try:
                            inp = page.locator(sel)
                            n = await inp.count()
                            # Duyệt HẾT các match, chọn ô ĐANG HIỂN THỊ (Google có input ẩn ở đầu DOM)
                            for _i in range(n):
                                el = inp.nth(_i)
                                try:
                                    if not await el.is_visible():
                                        continue
                                except Exception:
                                    continue
                                log_fn(f"  Nhập recovery: {recovery}")
                                await el.click()
                                await page.wait_for_timeout(200)
                                try:
                                    await el.fill("")
                                except Exception:
                                    await el.triple_click()
                                await el.press_sequentially(recovery, delay=40)
                                await page.wait_for_timeout(500)
                                await _click_next(page)
                                await page.wait_for_timeout(3000)
                                return True
                        except Exception:
                            pass
                    # Fallback: quét MỌI input đang hiển thị + nhập được (không phải hidden/checkbox)
                    try:
                        all_inp = page.locator('input:visible')
                        m = await all_inp.count()
                        for _j in range(m):
                            el = all_inp.nth(_j)
                            try:
                                itype = (await el.get_attribute("type") or "text").lower()
                                if itype in ("hidden", "checkbox", "radio", "submit", "button"):
                                    continue
                                if not await el.is_editable():
                                    continue
                            except Exception:
                                continue
                            log_fn(f"  Nhập recovery (fallback input hiển thị): {recovery}")
                            await el.click()
                            await page.wait_for_timeout(200)
                            try:
                                await el.fill("")
                            except Exception:
                                await el.triple_click()
                            await el.press_sequentially(recovery, delay=40)
                            await page.wait_for_timeout(500)
                            await _click_next(page)
                            await page.wait_for_timeout(3000)
                            return True
                    except Exception:
                        pass
                    # Chưa thấy ô input → nếu vẫn ở trang selection, click lại option recovery
                    if "selection" in page.url:
                        try:
                            await _select_recovery_option()
                        except Exception:
                            pass
                    await page.wait_for_timeout(1000)
                # Debug: log các input hiện có để chẩn đoán
                try:
                    _ins = await page.locator('input').count()
                    log_fn(f"  [recovery] Không thấy ô nhập sau 12s. URL={page.url[:80]} (inputs={_ins})")
                except Exception:
                    pass
                return False

            # 1) Ưu tiên 2FA (TOTP) nếu có secret
            if totp_secret and not _is_logged_in(page.url):
                for _try in range(2):
                    if await _try_totp(page, totp_secret, log_fn):
                        await page.wait_for_timeout(2000)
                        if _is_logged_in(page.url) or "totp" not in page.url.lower():
                            break
                    else:
                        break

            # 2) Recovery email: nếu có selection page → click dòng 3 → nhập mail
            if recovery and not _is_logged_in(page.url) and "challenge" in page.url:
                # Trang xác minh 2 bước (account ĐÃ CÓ 2FA: /skotp, /totp) hoặc verify-device
                # (/wa, /iap...) → bấm "Thử cách khác" để chuyển sang xác minh bằng recovery,
                # KHÔNG gõ recovery vào ô nhập MÃ.
                if any(k in page.url for k in ["/challenge/wa", "/challenge/iap",
                        "/challenge/skotp", "/challenge/totp", "/challenge/ipp",
                        "/challenge/dp", "/challenge/az"]):
                    log_fn("  [2step] Trang xác minh 2 bước → bấm 'Thử cách khác'…")
                    for _t in ["Thử cách khác", "Try another way", "More options",
                               "Cách khác"]:
                        try:
                            _el = page.locator(
                                f'a:has-text("{_t}"), button:has-text("{_t}"), '
                                f'[role="link"]:has-text("{_t}"), [role="button"]:has-text("{_t}")')
                            if await _el.count() > 0 and await _el.first.is_visible():
                                await _el.first.click()
                                log_fn(f"  [2step] Click '{_t}' OK")
                                await page.wait_for_timeout(2500)
                                break
                        except Exception:
                            pass
                    # Sau 'Thử cách khác' → trang chọn phương thức → chọn recovery email
                    await _select_recovery_option()
                    await page.wait_for_timeout(1500)
                # Nếu đang ở trang selection, click vào tuỳ chọn recovery email
                if "selection" in page.url:
                    await _select_recovery_option()
                    # Nếu vẫn ở selection (e.g. sau Thử cách khác ở trang mới), thử lại
                    if "selection" in page.url:
                        await page.wait_for_timeout(1000)
                        await _select_recovery_option()
                # Nhập recovery email
                await page.wait_for_timeout(2000)
                if not _is_logged_in(page.url):
                    entered = await _enter_recovery_email()
                    if not entered and "challenge" in page.url:
                        # Thử lại sau 2s
                        await page.wait_for_timeout(2000)
                        await _enter_recovery_email()

            # 2b) Ngay sau recovery, Google hay chèn trang 'Đảm bảo…' (Huỷ) /
            #     'Video selfie' (Để sau) — dọn luôn, không đợi tới cuối.
            for _n in range(5):
                _did = False
                if await _skip_keep_signin_page(page, log_fn):
                    _did = True
                if await _skip_selfie_video(page, log_fn):
                    _did = True
                if not _did:
                    break
                await page.wait_for_timeout(1500)

            # 3) Vẫn còn challenge → thử 2FA lại rồi chờ can thiệp tay
            if "challenge" in page.url and not _is_logged_in(page.url):
                if totp_secret:
                    await _try_totp(page, totp_secret, log_fn)
                    await page.wait_for_timeout(2000)
            if "challenge" in page.url and not _is_logged_in(page.url):
                log_fn("  ⚠ Chờ trang chuyển (nudge 'Đảm bảo…' / xác minh)...")
                for i in range(60, 0, -5):
                    # Trang nudge (Đảm bảo / selfie) = đã đăng nhập → xử lý & thoát sớm
                    if await _on_keep_signin_page(page) or await _on_selfie_page(page):
                        log_fn("  ✅ Thấy trang nudge (Đảm bảo/selfie) → đã đăng nhập, thoát chờ")
                        await _skip_keep_signin_page(page, log_fn)
                        await _skip_selfie_video(page, log_fn)
                        break
                    if _is_logged_in(page.url):
                        break
                    # FAIL-FAST: Google báo recovery sai / CAPTCHA / quá nhiều lần → dừng ngay
                    try:
                        _emsg = (await _read_error_text(page)).lower()
                    except Exception:
                        _emsg = ""
                    if any(k in _emsg for k in ["không đúng", "wrong", "incorrect",
                                                "quá nhiều lần", "too many", "sai"]):
                        log_fn(f"  ✗ Xác minh thất bại ({_emsg[:50]}) — dừng chờ")
                        break
                    if "recaptcha" in page.url.lower() or "captcha" in _emsg:
                        log_fn("  ✗ CAPTCHA — dừng chờ")
                        break
                    await page.wait_for_timeout(5000)
                    log_fn(f"    ...đợi {i}s")

        # ── Chờ trang ổn định sau recovery rồi kết luận ──────────
        # QUAN TRỌNG: sau khi nhập recovery, Google chuyển sang trang 'Đảm bảo…'
        # (hoặc video selfie) sau VÀI GIÂY. Nếu kết luận ngay -> tưởng thất bại -> thoát.
        # Vì vậy POLL tối đa ~18s: hễ đã đăng nhập / thấy trang nudge thì coi là THÀNH CÔNG.
        _on_nudge = False
        for _w in range(12):
            # Trang nudge (Đảm bảo / video selfie) = ĐÃ đăng nhập → thử bấm qua rồi thoát
            if await _on_keep_signin_page(page) or await _on_selfie_page(page):
                _on_nudge = True
                await _skip_keep_signin_page(page, log_fn)   # best-effort
                await _skip_selfie_video(page, log_fn)       # best-effort
                break
            if _is_logged_in(page.url):
                break
            await page.wait_for_timeout(1500)

        final_url = page.url
        success = (_is_logged_in(final_url) or _on_nudge
                   or await _on_keep_signin_page(page) or await _on_selfie_page(page))
        if success and not _is_logged_in(final_url):
            log_fn("  ✅ Đã đăng nhập (trang nudge 'Đảm bảo…/selfie') — đi tiếp, KHÔNG thoát")

        if success:
            log_fn(f"  ✅ Đăng nhập thành công")
            # Bỏ qua các popup Google sau khi login (recovery info, địa chỉ, v.v.)
            await _dismiss_post_login_prompts(page, log_fn)
        else:
            # DEBUG: chụp trang cuối lúc login fail để chẩn đoán (không tốn thêm mail)
            try:
                await page.screenshot(path=_dbg_path("debug_login_fail.png"))
                _dbg_body = (await page.inner_text("body"))[:400]
                log_fn(f"  [DEBUG login-fail] URL={page.url[:90]}")
                log_fn(f"  [DEBUG login-fail] Body: {_dbg_body[:300]}")
            except Exception:
                pass
            # Đọc text lỗi để phân loại chính xác
            try:
                ftxt = (await page.inner_text("body"))[:2500].lower()
            except Exception:
                ftxt = ""
            ferr = await _read_error_text(page)
            flow = (ferr + " " + ftxt).lower()
            reason = None
            if any(k in flow for k in ["disabled", "vô hiệu", "bị tắt",
                                       "account has been disabled"]):
                reason = "DISABLED | Tài khoản Gmail bị vô hiệu hoá"
            elif "challenge/totp" in final_url or "totp" in final_url.lower():
                reason = f"SAI_2FA | Mã 2FA không đúng / hết hạn | {ferr[:100]}"
            elif any(k in flow for k in ["wrong code", "mã không đúng", "không đúng mã",
                                         "sai mã", "code you entered", "invalid code"]):
                reason = f"SAI_2FA | {ferr[:110]}"
            elif "recovery" in final_url.lower() or any(
                    k in flow for k in ["recovery email", "email khôi phục",
                                        "khôi phục không", "confirm the recovery"]):
                reason = f"SAI_RECOVERY | Email khôi phục không đúng | {ferr[:90]}"
            elif any(k in flow for k in ["kiểm tra điện thoại", "check your phone",
                                         "thông báo đến điện thoại", "notification to your phone",
                                         "nhấn vào có", "tap yes", "trên điện thoại để xác minh",
                                         "on your phone to verify", "查看您的手机", "手机上的通知",
                                         "फ़ोन देखें", "अपने फ़ोन पर"]):
                reason = "PHONE_CHECK | Kiểm tra điện thoại (Google gửi thông báo lên máy — duyệt tay)"
            elif "challenge" in final_url or any(
                    k in flow for k in ["verify", "xác minh", "unusual",
                                        "bất thường", "captcha", "phone",
                                        "số điện thoại", "xác nhận"]):
                reason = f"VERIFY | Cần xác minh (điện thoại/thiết bị lạ) | {final_url[:70]}"
            else:
                reason = f"CHUA_RO | {final_url[:80]}"
            log_fn(f"  ⚠ Thất bại: {reason[:90]}")
            channel_handle = None
            await page.wait_for_timeout(500)
            return False, reason, None

        # Lấy YouTube channel handle sau khi login thành công
        channel_handle = None
        if success:
            channel_handle = await _capture_yt_handle(page, log_fn)

        # Không đóng browser → để user kiểm tra
        return success, final_url, channel_handle


# ══════════════════════════════════════════════════════════════════════════════
# TẠO 2FA / ĐỔI 2FA
# ══════════════════════════════════════════════════════════════════════════════

async def _reauth_if_needed(page, password: str, log_fn):
    """Nếu Google yêu cầu nhập lại mật khẩu giữa chừng, điền vào."""
    try:
        await page.wait_for_timeout(1500)
        pwd_inp = page.locator('input[type="password"]')
        if await pwd_inp.count() > 0 and await pwd_inp.first.is_visible():
            log_fn("  ↩ Yêu cầu nhập lại mật khẩu…")
            await pwd_inp.first.fill(password)
            await page.wait_for_timeout(400)
            await _click_next(page)
            await page.wait_for_timeout(2000)
    except Exception:
        pass


async def _get_totp_secret_from_page(page, log_fn) -> str:
    """
    Đọc TOTP secret từ trang setup authenticator.
    Google hiển thị secret dạng 'XXXX XXXX XXXX …' khi bấm 'Không thể quét?'.
    Trả về chuỗi secret không khoảng trắng.
    """
    import re as _re
    # Thử các selector phổ biến
    for sel in [
        'li[class*="secret"] span',
        '[data-secret]',
        'span[jsname="B3Eoc"]',
        'div[jsname="B3Eoc"]',
        'span.a7MBX',
        'span[aria-label]',
        '.EWTeR span',
        'pre',
    ]:
        try:
            el = page.locator(sel)
            cnt = await el.count()
            for idx in range(cnt):
                txt = (await el.nth(idx).inner_text()).strip()
                clean = txt.replace(" ", "").upper()
                if _valid_b32_secret(clean):
                    log_fn(f"  Secret selector={sel}: {clean[:8]}…")
                    return clean
        except Exception:
            pass

    # Fallback 1: inner_text toàn trang (đáng tin hơn HTML)
    try:
        body_text = await page.inner_text("body")
        body_upper = body_text.upper()
        _pats = [
            r'([A-Z2-7]{4}(?:[ \xa0][A-Z2-7]{4}){3,})',   # secret dạng nhóm 4 (chuẩn Google)
            r'([A-Z2-7]{16,32})',                          # chuỗi liền (fallback)
        ]
        for _pi, pat in enumerate(_pats):
            for m in _re.findall(pat, body_upper):
                clean = _re.sub(r'[\s\xa0]', '', m)
                if not _valid_b32_secret(clean):
                    continue
                # Pattern chuỗi LIỀN (_pi==1) DỄ bắt nhầm CHỮ trên trang thành secret rác —
                # vd 'AUTHENTICATOR', 'GOOGLEAUTHENTICATOR' (khi nút 'Không thể quét' chưa bấm
                # được nên secret thật chưa hiện). Secret Google THẬT hầu như luôn có CHỮ SỐ
                # (2-7); các từ tiếng Anh thì KHÔNG → yêu cầu có ≥1 chữ số để loại chữ rác.
                if _pi == 1 and not any(c in "234567" for c in clean):
                    log_fn(f"  ⚠ Bỏ qua chuỗi nghi là CHỮ (không có số): {clean[:16]}…")
                    continue
                log_fn(f"  Secret (inner_text): {clean[:8]}…")
                return clean
    except Exception:
        pass

    # (ĐÃ BỎ fallback quét page.content() HTML thô — nó bắt nhầm CSS 'padding:24px…'
    #  thành secret rác '24PX24PX…'. Secret thật luôn nằm trong chữ HIỂN THỊ (inner_text).)
    return ""


def _norm_txt(s: str) -> str:
    """Chuẩn hoá text: đổi MỌI dấu nháy cong -> nháy thẳng, gộp khoảng trắng, lower.
    Google render 'Can't scan it?' bằng nháy cong U+2019 -> has-text('Can\\'t') ASCII KHÔNG khớp."""
    if not s:
        return ""
    for ch in ("’", "‘", "ʼ", "′", "´", "`"):
        s = s.replace(ch, "'")
    s = s.replace("\xa0", " ")
    return " ".join(s.split()).strip().lower()


# Cụm text (đã chuẩn hoá) CHỈ khớp LINK 'Không thể quét? / Can't scan it?'
# (KHÔNG khớp câu hướng dẫn 'Choose Scan a QR code').
_CANT_SCAN_NEEDLES = (
    "can't scan", "cant scan", "không thể quét", "khong the quet",
    "स्कैन नहीं कर",                              # Hindi (इसे स्कैन नहीं कर पा रहे हैं?)
    "无法扫描", "无法扫码", "扫描不了", "無法掃描", "無法掃瞄",   # zh-CN / zh-TW
    "스캔할 수 없", "스캔이 안", "스캔되지 않",              # Korean
    "スキャンできない", "スキャンできません", "読み取れない",   # Japanese
    "สแกนไม่ได้",                                # Thai
    "no puedes escanear", "no puede escanear", "no se puede escanear",  # es
    "não consegue ler", "não consegue fazer a leitura", "não é possível ler",
    "não consegue digitalizar", "não consegue fazer a digitalização",   # pt
    "impossible de scanner", "vous ne pouvez pas scanner", "impossible de lire",  # fr
    "ne parvenez pas à", "vous ne parvenez pas", "impossible de numériser",       # fr (biến thể)
    "nicht scannen", "lässt sich nicht scannen", "nicht scannen können",  # de
    "tidak dapat memindai", "tidak bisa memindai",         # id
    "tidak dapat mengimbas", "tidak boleh mengimbas",      # ms
    "не удается отсканировать", "не удаётся отсканировать", "не получается",  # ru
    "يتعذّر", "لا يمكنك مسح", "تعذّر المسح",                # ar
    "tarayamıyor",                              # tr
    "non riesci a eseguire la scansione", "impossibile eseguire la scansione",  # it
)


async def _cant_scan_gone(page) -> bool:
    """True nếu link 'Can't scan it?' KHÔNG còn trên trang → đã chuyển sang xem
    secret dạng text ('Enter this text…' / 'Nhập mã này…')."""
    try:
        for fr in page.frames:
            try:
                t = _norm_txt(await fr.inner_text("body"))
            except Exception:
                continue
            if any(n in t for n in _CANT_SCAN_NEEDLES):
                return False
        return True
    except Exception:
        return False


async def _click_cant_scan(page, log_fn) -> bool:
    """Bấm 'Không thể quét mã?' / 'Can't scan it?' để Google hiện secret dạng text.
    - Chống dấu nháy cong: so khớp text đã chuẩn hoá.
    - Chống click-không-ăn (click vào span bọc, JS không bubble): click THEO TOẠ ĐỘ chuột.
    - VERIFY: sau khi click, link phải biến mất mới coi là thành công (thử ứng viên kế tiếp)."""
    if await _cant_scan_gone(page):
        return True   # đã ở màn secret rồi
    try:
        frames = list(page.frames)
    except Exception:
        frames = [page]
    for fr in frames:
        try:
            loc = fr.locator('a, button, [role="button"], [jsname], span')
            cnt = await loc.count()
        except Exception:
            continue
        for i in range(min(cnt, 600)):
            el = loc.nth(i)
            try:
                if not await el.is_visible():
                    continue
                t = _norm_txt(await el.inner_text())
                if not t or len(t) > 40:
                    continue
                if not any(n in t for n in _CANT_SCAN_NEEDLES):
                    continue
                # 1) click thường/force/JS
                await _click_el(el)
                # 2) click theo TOẠ ĐỘ (đáng tin nhất cho link custom của Google)
                try:
                    bb = await el.bounding_box()
                    if bb and bb["width"] > 0:
                        await page.mouse.click(bb["x"] + bb["width"] / 2,
                                               bb["y"] + bb["height"] / 2)
                except Exception:
                    pass
                await page.wait_for_timeout(1300)
                # 3) VERIFY: link đã mất → đã hiện secret
                if await _cant_scan_gone(page):
                    log_fn("  ✓ Click 'Không thể quét? / Can't scan it?' → đã hiện secret")
                    return True
            except Exception:
                pass
    # Debug: log URL + buttons hiện có để chẩn đoán
    try:
        log_fn(f"  [cant_scan] URL: {page.url[:90]}")
        btns = await page.locator('button, a, [role="button"]').all_inner_texts()
        visible_btns = [b.strip() for b in btns if b.strip()][:15]
        log_fn(f"  [cant_scan] Buttons/Links: {visible_btns}")
    except Exception:
        pass
    return False




async def _click_confirm_2fa(page, log_fn) -> bool:
    """Bấm nút XÁC NHẬN mã 2FA (Verify/Xác minh/Verifikasi…) — ĐA NGÔN NGỮ, và TUYỆT ĐỐI
    KHÔNG bấm nút Huỷ/Quay lại. Trả True nếu bấm được đúng nút xác nhận."""
    # 1) Khớp trực tiếp text Verify/Next, loại nút Huỷ/Back
    for fr in page.frames:
        for tv in _VERIFY_TXT + _NEXT_TXT:
            try:
                loc = fr.locator(f'button:has-text("{tv}"), [role="button"]:has-text("{tv}"), '
                                 f'a:has-text("{tv}")')
                for i in range(min(await loc.count(), 6)):
                    el = loc.nth(i)
                    if not await el.is_visible():
                        continue
                    t = ((await el.inner_text()) or "").strip().lower()
                    if any(c in t for c in _CANCEL_KW):
                        continue
                    if await _click_el(el):
                        log_fn(f"  ✓ Bấm xác nhận 2FA: '{t[:24]}'")
                        return True
            except Exception:
                pass
    # 2) Fallback AN TOÀN: nút CUỐI (bên phải) trong hộp thoại mà KHÔNG phải Huỷ/Back
    for sel in ('[role="dialog"]', 'tp-yt-paper-dialog', 'ytcp-dialog',
                'c-wiz', 'form'):
        for fr in page.frames:
            try:
                dlg = fr.locator(sel)
                if await dlg.count() == 0:
                    continue
                btns = dlg.first.locator('button, [role="button"], a[role="button"]')
                nb = await btns.count()
                for i in range(nb - 1, -1, -1):   # từ phải qua trái: nút Verify thường ở cuối
                    b = btns.nth(i)
                    try:
                        if not await b.is_visible():
                            continue
                        t = ((await b.inner_text()) or "").strip().lower()
                        if not t or len(t) > 30 or any(c in t for c in _CANCEL_KW):
                            continue
                        if await _click_el(b):
                            log_fn(f"  ✓ Bấm nút xác nhận cuối hộp thoại: '{t[:24]}'")
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
    return False


async def _verify_totp_and_confirm(page, secret: str, log_fn) -> bool:
    """Nhập TOTP code + bấm Xác minh. Trả về True nếu thành công."""
    if not _valid_b32_secret(secret):
        log_fn(f"  ✗ Secret không hợp lệ (không phải base32): {str(secret)[:16]!r}")
        return False
    # Ô "Nhập mã" (để ĐIỀN) — rộng, đa ngôn ngữ
    _code_sels = [
        'input[type="tel"]',
        'input[name="Pin"]',
        'input[autocomplete="one-time-code"]',
        'input[aria-label*="mã" i]',
        'input[placeholder*="mã" i]',
        'input[aria-label*="code" i]',
        'input[placeholder*="Code" i]',
        'input[aria-label*="kode" i]', 'input[placeholder*="kode" i]',   # Indonesia/Malay
        'input[aria-label*="código" i]', 'input[placeholder*="código" i]',  # es/pt
        'input[aria-label*="код" i]', 'input[placeholder*="код" i]',      # ru
        'input[type="number"]',
        # fallback: ô nhập trong hộp thoại (đa ngôn ngữ, khi placeholder không khớp)
        '[role="dialog"] input[type="text"]',
        '[role="dialog"] input:not([type="hidden"]):not([type="checkbox"])',
    ]
    # Ô mã TOTP CHẶT — CHỈ dùng để kiểm tra 'ô nhập mã còn hiện không'.
    # PHẢI thật hẹp: chỉ đúng ô TOTP (tel/Pin/totpPin/one-time-code); các selector chung
    # (aria-label 'mã'/'code'…) BẮT BUỘC nằm trong [role=dialog] để KHÔNG khớp nhầm ô tìm
    # kiếm / input khác trên TRANG THÀNH CÔNG (nguyên nhân báo nhầm 'thất bại' dù đã đổi).
    _strict_code_sels = ['input[type="tel"]', 'input[name="Pin"]', 'input#totpPin',
                         'input[autocomplete="one-time-code"]',
                         '[role="dialog"] input[type="number"]',
                         '[role="dialog"] input[aria-label*="mã" i]',
                         '[role="dialog"] input[placeholder*="mã" i]',
                         '[role="dialog"] input[aria-label*="code" i]',
                         '[role="dialog"] input[placeholder*="code" i]',
                         '[role="dialog"] input[aria-label*="kode" i]']
    _wrong_kw = ["không chính xác", "sai mã", "mã không đúng", "wrong", "incorrect",
                 "invalid", "try again", "验证码有误", "验证码错误", "不正确", "错误",
                 "驗證碼錯誤", "잘못된", "올바르지", "正しくありません", "コードが正しく",
                 "गलत", "código incorrecto", "code incorrect", "falscher code", "salah",
                 "неверный код", "رمز غير صحيح", "รหัสไม่ถูกต้อง"]

    async def _find_code_input():
        for _poll in range(14):
            # Quét ô nhập mã trong MỌI frame (không chỉ frame chính — dialog có thể ở iframe).
            try:
                _frames = list(page.frames)
            except Exception:
                _frames = [page]
            for fr in _frames:
                for sel in _code_sels:
                    try:
                        inp = fr.locator(sel)
                        if await inp.count() > 0 and await inp.first.is_visible():
                            return inp.first
                    except Exception:
                        pass
            # Chưa thấy ô mã → có thể còn KẸT ở màn hiện secret (chưa sang ô nhập mã) → bấm
            # 'Tiếp theo' bằng _click_in_frames (mạnh hơn: mọi frame + JS-click). Nếu đã ở màn
            # nhập mã thì nút này không còn → no-op (an toàn).
            if _poll in (1, 4, 7, 10):
                try:
                    await _click_dialog_next(page, log_fn)
                except Exception:
                    pass
            await page.wait_for_timeout(700)
        # Vẫn không thấy ô mã → CHỤP ẢNH + liệt kê nút để chẩn đoán account bị kẹt ở đâu.
        try:
            await page.screenshot(path=_dbg_path("debug_no_code_input.png"), timeout=5000)
            _btns = [b.strip() for b in (await page.locator(
                'button, a, [role="button"]').all_inner_texts()) if b.strip()][:25]
            log_fn(f"  [DEBUG] Kẹt: không thấy ô nhập mã. URL={page.url[:90]} | Nút: {_btns}")
        except Exception:
            pass
        return None

    async def _code_field_gone():
        for sel in _strict_code_sels:
            try:
                if await page.locator(sel).first.is_visible():
                    return False
            except Exception:
                pass
        return True

    # === NHẬP MÃ + XÁC MINH, THỬ LẠI tối đa 3 lần bằng mã MỚI ===
    # Vì sao thử lại: mã TOTP chỉ sống 30s. Proxy chậm / bấm trúng cuối chu kỳ → mã hết hạn
    # giữa lúc nhập & bấm → Google TỪ CHỐI dù secret ĐÚNG. Thử lại bằng mã MỚI (chờ sang chu
    # kỳ mới) sẽ qua. Nếu secret SAI thật → cả 3 lần đều trượt → return False (KHÔNG lưu = an toàn).
    _tried_codes = set()
    for _attempt in range(3):
        try:
            code = totp_now(secret)
        except Exception as _e:
            log_fn(f"  ✗ Sinh mã TOTP lỗi: {_e}")
            return False
        # Bảo đảm là mã MỚI (chưa thử): chờ sang chu kỳ 30s tiếp theo nếu trùng
        _waited = 0
        while code in _tried_codes and _waited < 34:
            await page.wait_for_timeout(2000)
            _waited += 2
            try:
                code = totp_now(secret)
            except Exception:
                break
        _tried_codes.add(code)

        inp = await _find_code_input()
        if inp is None:
            log_fn("  ✗ Không thấy ô nhập mã 2FA → THẤT BẠI (KHÔNG lưu secret)")
            return False
        try:
            await inp.click()
            try:
                await inp.fill("")
            except Exception:
                pass
            await inp.fill(code)
        except Exception as _fe:
            log_fn(f"  ✗ Điền mã lỗi: {_fe}")
            return False
        log_fn(f"  ✓ Nhập TOTP (lần {_attempt+1}/3): {code}")
        await page.wait_for_timeout(400)

        # CHỈ bấm nút Verify — TUYỆT ĐỐI KHÔNG bấm Huỷ/Back (bấm nhầm Huỷ = huỷ đổi 2FA
        # nhưng ô mã cũng mất → tool tưởng xong → lưu secret sai → mất account).
        if not await _click_confirm_2fa(page, log_fn):
            log_fn("  ✗ Không thấy nút Xác minh (có thể chỉ có Huỷ) → KHÔNG lưu secret")
            return False

        # Chờ kết quả. ƯU TIÊN: ô mã ĐÓNG = THÀNH CÔNG (tín hiệu dương, chắc nhất).
        # Chỉ khi ô mã VẪN còn + có chữ lỗi → mã sai → thử mã MỚI ở vòng sau.
        _rejected = False
        _rej_err = ""
        for _chk in range(7):
            await page.wait_for_timeout(1000)
            if await _code_field_gone():
                log_fn(f"  ✓ 2FA xác minh THÀNH CÔNG (ô nhập mã đã đóng) — lần {_attempt+1}")
                return True
            # CHỈ tin Ô BÁO LỖI RIÊNG của Google (aria-live / jsname lỗi). TUYỆT ĐỐI KHÔNG
            # quét toàn trang — quét toàn trang dễ dính nhầm chữ 'sai/incorrect/错误…' ở chỗ
            # khác (hướng dẫn, template ẩn) → báo nhầm MÃ ĐÚNG là bị từ chối → thử lại tới
            # hỏng dù Google ĐÃ nhận mã. Đây chính là lỗi 'nhập đúng mà báo thất bại'.
            err = (await _read_error_text(page) or "").strip().lower()
            if err and any(k in err for k in _wrong_kw):
                _rejected = True
                _rej_err = err[:80]
                break
        if _rejected:
            log_fn(f"  ⚠ Google từ chối mã (lần {_attempt+1}/3): '{_rej_err}' → thử lại bằng mã MỚI…")
            try:
                inp2 = await _find_code_input()
                if inp2 is not None:
                    await inp2.click()
                    await inp2.fill("")
            except Exception:
                pass
            continue
        log_fn(f"  ⚠ Chưa qua bước xác minh (lần {_attempt+1}/3) → thử lại…")

    log_fn("  ✗ Thử nhiều mã vẫn không xác minh được 2FA mới → KHÔNG lưu secret (an toàn)")
    return False


async def _click_exact(page, names, log_fn=None, tag="", click_timeout=4000) -> bool:
    """Click n\u00fat c\u00f3 text CH\u00cdNH X\u00c1C b\u1eb1ng 'names' (tr\u00e1nh 'B\u1eadt' kh\u1edbp nh\u1ea7m 'B\u1eadt t\u00ednh n\u0103ng\u2026')."""
    for nm in names:
        for sel in ['button', 'a', '[role="button"]']:
            try:
                loc = page.locator(sel)
                n = await loc.count()
                for i in range(min(n, 30)):
                    el = loc.nth(i)
                    try:
                        if not await el.is_visible():
                            continue
                        txt = (await el.inner_text()).strip()
                        if txt == nm:
                            await el.click(timeout=click_timeout)
                            if log_fn:
                                log_fn(f"  {tag}\u2713 Click '{nm}'")
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
    return False


async def _post_2fa_activate(page, log_fn) -> bool:
    """
    Sau khi X\u00e1c minh TOTP, b\u1eadt h\u1eb3n 2FA (\u0111\u00fang flow ng\u01b0\u1eddi d\u00f9ng \u0111\u00e3 ch\u1ec9):
      1. Trang '\u1ee8ng d\u1ee5ng Authenticator' \u2192 n\u00fat 'B\u1eadt' (b\u1eadt X\u00e1c minh 2 b\u01b0\u1edbc)
      2. Trang 'X\u00e1c minh 2 b\u01b0\u1edbc' \u2192 n\u00fat 'B\u1eadt t\u00ednh n\u0103ng X\u00e1c minh 2 b\u01b0\u1edbc'
      3. Popup 'Th\u00eam s\u1ed1 \u0111i\u1ec7n tho\u1ea1i\u2026?' \u2192 'B\u1ecf qua'
      4. Popup th\u00e0nh c\u00f4ng \u2192 'Xong'
    Tr\u1ea3 True n\u1ebfu x\u00e1c nh\u1eadn \u0111\u01b0\u1ee3c 2FA \u0111\u00e3 b\u1eadt.
    """
    log_fn(f"  [post2fa] B\u1eaft \u0111\u1ea7u b\u1eadt 2 b\u01b0\u1edbc. URL={page.url[:70]}")

    async def _try_bat():
        return await _click_in_frames(page, ["B\u1eadt", "Turn on"], log_fn, tag="[post2fa] ")

    async def _turnon():
        return await _click_in_frames(
            page, ["B\u1eadt t\u00ednh n\u0103ng X\u00e1c minh 2 b\u01b0\u1edbc", "Turn on 2-Step Verification"],
            log_fn, tag="[post2fa] ")

    async def _need_second_step() -> bool:
        # Popup 'Th\u00eam c\u00e1c b\u01b0\u1edbc th\u1ee9 hai v\u00e0o t\u00e0i kho\u1ea3n' = trang CH\u01afA c\u1eadp nh\u1eadt k\u1ecbp
        # tr\u1ea1ng th\u00e1i authenticator (c\u1ea7n th\u1eddi gian) \u2192 kh\u00f4ng ph\u1ea3i l\u1ed7i th\u1eadt.
        try:
            for fr in page.frames:
                try:
                    t = (await fr.inner_text("body"))[:3000].lower()
                except Exception:
                    continue
                if ("th\u00eam c\u00e1c b\u01b0\u1edbc th\u1ee9 hai v\u00e0o t\u00e0i kho\u1ea3n" in t
                        or "h\u00e3y th\u00eam c\u00e1c b\u01b0\u1edbc th\u1ee9 hai" in t
                        or "add a second step" in t):
                    return True
        except Exception:
            pass
        return False

    # B\u01b0\u1edbc 1+2 c\u00f3 retry: n\u1ebfu Google b\u00e1o 'ch\u01b0a c\u00f3 b\u01b0\u1edbc th\u1ee9 hai' (do trang ch\u01b0a c\u1eadp nh\u1eadt k\u1ecbp)
    # \u2192 b\u1ea5m 'Quay l\u1ea1i' \u2192 F5 reload \u2192 CH\u1edc trang c\u1eadp nh\u1eadt \u2192 th\u1eed B\u1eadt l\u1ea1i (t\u1ed1i \u0111a 3 l\u1ea7n).
    for _attempt in range(3):
        if await _wait_for(page, _try_bat, timeout=14000):
            await page.wait_for_timeout(3500)   # ch\u1edd trang c\u1eadp nh\u1eadt authenticator
        if await _wait_for(page, _turnon, timeout=11000):
            await page.wait_for_timeout(2500)
        if await _need_second_step():
            log_fn(f"  [post2fa] Trang ch\u01b0a c\u1eadp nh\u1eadt (popup 'Th\u00eam b\u01b0\u1edbc th\u1ee9 hai') "
                   f"\u2192 Quay l\u1ea1i + F5 (l\u1ea7n {_attempt+1}/3)")
            await _click_in_frames(page, ["Quay l\u1ea1i", "Back"], log_fn, tag="[post2fa] ")
            await page.wait_for_timeout(1500)
            try:
                await page.reload(wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            await page.wait_for_timeout(6000)   # F5 xong, ch\u1edd authenticator hi\u1ec7n l\u00ean
            continue
        break

    # 3+4) D\u1ecdn popup sau khi b\u1eadt: 'B\u1ecf qua' (th\u00eam S\u0110T) v\u00e0 'Xong' (th\u00e0nh c\u00f4ng).
    #      Th\u1ee9 t\u1ef1/th\u1eddi \u0111i\u1ec3m 2 popup n\u00e0y thay \u0111\u1ed5i \u2192 L\u1eb6P b\u1ea5m nhi\u1ec1u v\u00f2ng (~18s) cho ch\u1eafc \u0103n.
    async def _2fa_on() -> bool:
        try:
            _b = ""
            for fr in page.frames:
                try:
                    _b += " " + (await fr.inner_text("body")).lower()
                except Exception:
                    pass
            return any(k in _b for k in [
                "t\u1eaft x\u00e1c minh 2 b\u01b0\u1edbc", "\u0111\u01b0\u1ee3c b\u1ea3o v\u1ec7 b\u1eb1ng t\u00ednh n\u0103ng x\u00e1c minh 2 b\u01b0\u1edbc",
                "turn off 2-step", "your account is protected"])
        except Exception:
            return False

    _done_clicked = False
    for _r in range(10):
        _clicked = False
        if await _click_in_frames(page, ["B\u1ecf qua", "Skip"], log_fn, tag="[post2fa] "):
            _clicked = True
        if await _click_in_frames(page, ["Xong", "Done"], log_fn, tag="[post2fa] "):
            _clicked = True
            _done_clicked = True
        # B\u1ea5m Xong xong + x\u00e1c nh\u1eadn 2FA \u0111\u00e3 b\u1eadt \u2192 D\u1eeaNG ngay (kh\u1ecfi b\u1ea5m th\u1eeba)
        if _done_clicked and await _2fa_on():
            break
        if not _clicked:
            if _done_clicked or await _2fa_on():
                break
            await page.wait_for_timeout(1500)
        else:
            await page.wait_for_timeout(1000)
    if not _done_clicked:
        log_fn("  [post2fa] \u26a0 Kh\u00f4ng th\u1ea5y n\u00fat 'Xong' (c\u00f3 th\u1ec3 \u0111\u00e3 t\u1ef1 \u0111\u00f3ng)")

    # \u2500\u2500 X\u00c1C NH\u1eacN 2FA \u0110\u00c3 B\u1eacT \u2014 RELOAD \u0111\u1ec3 trang c\u1eadp nh\u1eadt tr\u1ea1ng th\u00e1i TH\u1eacT \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    await page.wait_for_timeout(1500)
    enabled = await _2fa_on()
    if not enabled:
        # Trang c\u00f3 th\u1ec3 ch\u01b0a c\u1eadp nh\u1eadt k\u1ecbp \u2192 F5 r\u1ed3i ki\u1ec3m tra l\u1ea1i
        log_fn("  [post2fa] Ch\u01b0a th\u1ea5y '\u0111\u00e3 b\u1eadt' \u2192 F5 ki\u1ec3m tra l\u1ea1i\u2026")
        try:
            await page.reload(wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
        except Exception:
            pass
        enabled = await _2fa_on()
        # V\u1eabn ch\u01b0a b\u1eadt + c\u00f2n banner 'B\u1eadt' \u2192 b\u1ea5m B\u1eadt l\u1ea7n cu\u1ed1i cho ch\u1eafc
        if not enabled and await _need_second_step() is False:
            log_fn("  [post2fa] Th\u1eed B\u1eadt l\u1ea7n cu\u1ed1i\u2026")
            if await _click_in_frames(page, ["B\u1eadt", "Turn on"], log_fn, tag="[post2fa] "):
                await page.wait_for_timeout(3000)
            if await _click_in_frames(page, ["B\u1eadt t\u00ednh n\u0103ng X\u00e1c minh 2 b\u01b0\u1edbc",
                                             "Turn on 2-Step Verification"], log_fn, tag="[post2fa] "):
                await page.wait_for_timeout(2500)
            await _click_in_frames(page, ["B\u1ecf qua", "Skip"], log_fn, tag="[post2fa] ")
            await _click_in_frames(page, ["Xong", "Done"], log_fn, tag="[post2fa] ")
            await page.wait_for_timeout(2500)
            enabled = await _2fa_on()

    _st = "\u0110\u00c3 B\u1eacT \u2713" if enabled else "CH\u01afA x\u00e1c nh\u1eadn (n\u00ean ki\u1ec3m tra tay)"
    log_fn(f"  [post2fa] 2FA {_st}")
    # Sau khi xong \u2192 \u0111\u1ee3i 5s r\u1ed3i m\u1edbi tho\u00e1t lu\u1ed3ng (tr\u00e1nh \u0111\u00f3ng browser qu\u00e1 nhanh)
    log_fn("  [post2fa] \u0110\u1ee3i 5s tr\u01b0\u1edbc khi k\u1ebft th\u00fac\u2026")
    await page.wait_for_timeout(5000)
    return enabled


async def _click_el(el, timeout=5000) -> bool:
    """Click 1 element; nếu click thường lỗi (element không actionable) → thử force + JS click."""
    try:
        await el.click(timeout=timeout)
        return True
    except Exception:
        pass
    try:
        await el.click(timeout=timeout, force=True)
        return True
    except Exception:
        pass
    try:
        await el.evaluate("e => e.click()")
        return True
    except Exception:
        return False


async def _click_in_frames(page, names, log_fn=None, tag="", timeout=5000) -> bool:
    """Tìm & click nút có text trong MỌI frame (kể cả iframe). Dùng force/JS click nếu cần."""
    try:
        frames = list(page.frames)
    except Exception:
        frames = [page]
    for fr in frames:
        for nm in names:
            finders = [
                lambda f=fr, n=nm: f.get_by_role("button", name=n, exact=True),
                lambda f=fr, n=nm: f.get_by_text(n, exact=True),
                lambda f=fr, n=nm: f.locator(
                    f'button:has-text("{n}"), a:has-text("{n}"), '
                    f'[role="button"]:has-text("{n}"), div[role="button"]:has-text("{n}")'),
            ]
            for mk in finders:
                try:
                    loc = mk()
                    cnt = await loc.count()
                    for i in range(min(cnt, 15)):
                        el = loc.nth(i)
                        try:
                            if await el.is_visible() and await _click_el(el, timeout):
                                if log_fn:
                                    log_fn(f"  {tag}✓ Click '{nm}'")
                                return True
                        except Exception:
                            pass
                except Exception:
                    pass
            # Cách 4: quét phần tử Google [jsname] có inner_text ĐÚNG = nm
            #  (nút 'Bật' của Google là <div/span jsname> không phải button/[role]).
            try:
                jl = fr.locator('[jsname]')
                jn = await jl.count()
                for i in range(min(jn, 400)):
                    el = jl.nth(i)
                    try:
                        if not await el.is_visible():
                            continue
                        if (await el.inner_text()).strip() == nm:
                            if await _click_el(el, timeout):
                                if log_fn:
                                    log_fn(f"  {tag}✓ Click '{nm}' (jsname)")
                                return True
                    except Exception:
                        pass
            except Exception:
                pass
    return False


async def _on_keep_signin_page(page) -> bool:
    """True nếu đang ở trang 'Đảm bảo rằng bạn luôn có thể đăng nhập' (quét mọi frame).
    Trang này chỉ xuất hiện SAU khi đã đăng nhập thành công → dùng làm dấu hiệu login OK."""
    try:
        for fr in page.frames:
            try:
                t = (await fr.inner_text("body"))[:2500].lower()
            except Exception:
                continue
            if ("luôn có thể đăng nhập" in t
                    or "make sure you can always sign in" in t
                    or "keep signing in" in t
                    or ("số điện thoại khôi phục" in t and "email khôi phục" in t)):
                return True
    except Exception:
        pass
    return False


async def _skip_keep_signin_page(page, log_fn) -> bool:
    """
    Trang 'Đảm bảo rằng bạn luôn có thể đăng nhập' → bấm 'Huỷ' (KHÔNG bấm 'Lưu').
    Quét MỌI frame vì Google có thể render trong iframe.
    """
    if not await _on_keep_signin_page(page):
        return False
    log_fn("  [keep-signin] Trang 'Đảm bảo…' → bấm 'Huỷ'")
    try:
        await page.screenshot(path=_dbg_path("debug_keep_signin.png"))
    except Exception:
        pass
    ok = await _click_in_frames(page, ["Huỷ", "Hủy", "Cancel"], log_fn, tag="[keep-signin] ")
    if ok:
        await page.wait_for_timeout(2000)
        return True
    log_fn("  [keep-signin] ⚠ Thấy trang nhưng KHÔNG bấm được 'Huỷ'")
    return False


async def _on_selfie_page(page) -> bool:
    """True nếu đang ở trang 'video selfie' (nudge sau đăng nhập, quét mọi frame)."""
    try:
        for fr in page.frames:
            try:
                t = (await fr.inner_text("body"))[:2000].lower()
            except Exception:
                continue
            if ("video selfie" in t or "quay video" in t
                    or "record a video selfie" in t):
                return True
    except Exception:
        pass
    return False


async def _skip_selfie_video(page, log_fn):
    """Trang 'Bảo vệ quyền truy cập bằng video selfie' → bấm 'Để sau' (quét mọi frame)."""
    detected = False
    try:
        for fr in page.frames:
            try:
                t = (await fr.inner_text("body"))[:2500].lower()
            except Exception:
                continue
            if ("video selfie" in t or "quay video" in t
                    or "record a video selfie" in t or "video selfie" in t):
                detected = True
                break
    except Exception:
        pass
    if not detected:
        return False
    log_fn("  [selfie] Trang video selfie → bấm 'Để sau'")
    try:
        await page.screenshot(path=_dbg_path("debug_selfie.png"))
    except Exception:
        pass
    ok = await _click_in_frames(page, ["Để sau", "Not now", "Later", "Skip"],
                                log_fn, tag="[selfie] ")
    if ok:
        await page.wait_for_timeout(2000)
        return True
    log_fn("  [selfie] ⚠ Thấy trang nhưng KHÔNG bấm được 'Để sau'")
    return False

async def _handle_challenge_selection(page, password: str, recovery_email: str, log_fn):
    """Xử lý trang Google challenge/selection (Xác minh danh tính)."""
    cur_url = page.url
    if not any(k in cur_url for k in ["challenge", "selection", "v3/signin"]):
        return
    log_fn(f"  ↩ Challenge page: {cur_url[:80]}")

    try:
        await page.screenshot(path=_dbg_path("debug_challenge.png"))
    except Exception:
        pass

    # ── BƯỚC 0: Đang ở trang NHẬP recovery email (có input field) ──
    if recovery_email:
        try:
            await page.wait_for_timeout(1000)
            inp = page.locator('input[type="email"], input[type="text"], input[name="knowledgePreregisteredEmailResponse"]')
            if await inp.count() > 0 and await inp.first.is_visible():
                await inp.first.click()
                await page.wait_for_timeout(300)
                await inp.first.triple_click()
                await inp.first.press_sequentially(recovery_email, delay=40)
                await page.wait_for_timeout(500)
                log_fn(f"  ↩ Đã nhập recovery email (input page): {recovery_email}")
                await _click_next(page)
                await page.wait_for_timeout(3000)
                return
        except Exception as _e0:
            log_fn(f"  ↩ [BUOC0] loi: {_e0}")

    # ── BƯỚC 1: Trang selection – click "Xác nhận gmail/email khôi phục" ──
    if recovery_email:
        for txt in ["Xác nhận Gmail khôi phục", "Xác nhận gmail khôi phục",
                    "Xác nhận email khôi phục", "Confirm recovery email",
                    "Confirm your recovery email", "Recovery email", "khôi phục"]:
            try:
                # Thu selector rong hon: bat ky element nao chua text nay
                el = page.locator(
                    f'li:has-text("{txt}"), [role="listitem"]:has-text("{txt}"), '
                    f'div[role="link"]:has-text("{txt}"), a:has-text("{txt}"), '
                    f'button:has-text("{txt}"), [tabindex]:has-text("{txt}")'
                )
                # Neu khong tim duoc, thu get_by_text
                _cnt = await el.count()
                if _cnt == 0:
                    el = page.get_by_text(txt, exact=False)
                if await el.count() > 0 and await el.first.is_visible():
                    await el.first.click()
                    log_fn(f"  ↩ Click recovery option ({txt!r})")
                    await page.wait_for_timeout(3000)
                    # Kiem tra trang nhap email
                    inp2 = page.locator('input[type="email"], input[type="text"], input[name="knowledgePreregisteredEmailResponse"]')
                    if await inp2.count() > 0 and await inp2.first.is_visible():
                        await inp2.first.click()
                        await page.wait_for_timeout(300)
                        await inp2.first.triple_click()
                        await inp2.first.press_sequentially(recovery_email, delay=40)
                        await page.wait_for_timeout(500)
                        await _click_next(page)
                        await page.wait_for_timeout(3000)
                        log_fn(f"  ↩ Đã nhập recovery email: {recovery_email}")
                    try:
                        await page.screenshot(
                            path=_dbg_path("debug_after_recovery.png"))
                    except Exception:
                        pass
                    return
            except Exception:
                pass
        log_fn("  ↩ Không tìm thấy tùy chọn recovery email")
        # DEBUG: chụp trang challenge để biết Google đang hỏi gì (vd challenge/ootp —
        # trang này KHÔNG có sẵn mục 'email khôi phục', phải bấm 'Thử cách khác' trước).
        try:
            await page.screenshot(path=_dbg_path("debug_challenge.png"), timeout=5000)
            _seen_ch = [t.strip() for t in await page.locator(
                'button, a, [role="button"], [role="listitem"], li'
            ).all_inner_texts() if t.strip()][:25]
            log_fn(f"  ↩ [DEBUG] Challenge URL={page.url[:90]} | Mục thấy: {_seen_ch}")
        except Exception:
            pass

    # ── BƯỚC 2: 'Thử cách khác' (ĐA NGÔN NGỮ, mọi frame) → ưu tiên EMAIL KHÔI PHỤC ──
    # Trang challenge/ootp (Google gửi mã tới nơi khác) KHÔNG hiện sẵn mục email khôi phục;
    # phải bấm 'Thử cách khác' để sang trang chọn phương thức rồi mới chọn được.
    _ANOTHER_WAY = ["Thử cách khác", "Try another way", "More options", "Cách khác",
                    "试试其他方式", "尝试其他方式", "嘗試其他方式", "其他方式",
                    "다른 방법 시도", "다른 방법", "別の方法を試す", "他の方法",
                    "ลองวิธีอื่น", "Probar otro método", "Tentar outro método",
                    "Essayer une autre méthode", "Andere Option testen",
                    "Coba cara lain", "Cuba cara lain", "Попробовать другой способ",
                    "جرّب طريقة أخرى", "Başka yöntem deneyin", "Prova un altro metodo"]
    if await _click_in_frames(page, _ANOTHER_WAY, log_fn, tag="↩ "):
        await page.wait_for_timeout(2500)
        # Sang trang chọn phương thức → ƯU TIÊN chọn 'Xác nhận email khôi phục'
        if recovery_email:
            for txt in ["Xác nhận Gmail khôi phục", "Xác nhận email khôi phục",
                        "Confirm your recovery email", "Confirm recovery email",
                        "email khôi phục", "recovery email"]:
                try:
                    el = page.locator(
                        f'li:has-text("{txt}"), [role="listitem"]:has-text("{txt}"), '
                        f'div[role="link"]:has-text("{txt}"), a:has-text("{txt}"), '
                        f'button:has-text("{txt}")')
                    if await el.count() > 0 and await el.first.is_visible():
                        await el.first.click()
                        log_fn(f"  ↩ Click email khôi phục sau 'Thử cách khác' ({txt!r})")
                        await page.wait_for_timeout(2500)
                        inp2 = page.locator(
                            'input[type="email"], input[type="text"], '
                            'input[name="knowledgePreregisteredEmailResponse"]')
                        if await inp2.count() > 0 and await inp2.first.is_visible():
                            await inp2.first.click()
                            await page.wait_for_timeout(300)
                            await inp2.first.press_sequentially(recovery_email, delay=40)
                            await page.wait_for_timeout(500)
                            await _click_next(page)
                            await page.wait_for_timeout(3000)
                            log_fn(f"  ↩ Đã nhập recovery email: {recovery_email}")
                        return
                except Exception:
                    pass

    for txt in ["Mật khẩu", "Password", "Enter your password"]:
        try:
            el = page.locator(
                f'li:has-text("{txt}"), a:has-text("{txt}"), '
                f'[role="listitem"]:has-text("{txt}")'
            )
            if await el.count() > 0 and await el.first.is_visible():
                await el.first.click()
                log_fn(f"  ↩ Click '{txt}'")
                await page.wait_for_timeout(2000)
                break
        except Exception:
            pass

    await _reauth_if_needed(page, password, log_fn)


async def _navigate_to_authenticator_page(page, password, old_totp_secret, log_fn, recovery_email=""):
    """Navigate đến trang Authenticator và xử lý re-auth."""
    log_fn("  Mở trang Authenticator…")
    # ĐIỀU HƯỚNG KIỂU NGƯỜI THẬT: page.goto thẳng tới /security bị Google trả bản
    # "general-light" (không có nút Authenticator) vì đó là điều hướng automation
    # (Sec-Fetch-Site: none). Thay vào đó mở google.com → CLICK avatar One Google Bar
    # → "Quản lý Tài khoản Google" (điều hướng same-origin bằng cú click) rồi sang /security.
    try:
        await page.goto("https://www.google.com/?hl=vi",
                        wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(2500)
        # Click avatar (góc phải trên)
        for _s in ['a[aria-label*="Tài khoản Google"]', 'a[href*="SignOutOptions"]',
                   'a[aria-label*="Google Account"]', 'a.gb_d', 'a.gb_A']:
            try:
                el = page.locator(_s)
                if await el.count() > 0 and await el.first.is_visible():
                    await el.first.click()
                    await page.wait_for_timeout(1800)
                    break
            except Exception:
                pass
        # Click "Quản lý Tài khoản Google" trong popup → sang myaccount (same-origin)
        for _t in ["Quản lý Tài khoản Google của bạn", "Quản lý Tài khoản Google",
                   "Manage your Google Account"]:
            try:
                el = page.locator(f'a:has-text("{_t}")')
                if await el.count() > 0 and await el.first.is_visible():
                    await el.first.click()
                    await page.wait_for_timeout(4000)
                    break
            except Exception:
                pass
    except Exception as _he:
        log_fn(f"  [human-nav] lỗi: {_he}")
    log_fn(f"  [human-nav] URL={page.url[:70]}")
    # Sang trang Xác minh 2 bước (twosv) bằng điều hướng same-origin (JS) khi đã ở trong
    # myaccount. twosv là trang FULL có nút Authenticator; /security dễ bị trả general-light.
    if "myaccount.google.com" in page.url:
        try:
            await page.evaluate(
                "(u) => { window.location.href = u; }", TWOSV_URL)
            await page.wait_for_timeout(4000)
        except Exception:
            pass
    else:
        await page.goto(TWOSV_URL, wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(3000)

    # Vòng lặp xử lý multi-step challenge:
    # Pass 1: trang nhập mật khẩu → nhập pass → Google hiện selection page
    # Pass 2: selection page → click 'Xác nhận email khôi phục' → nhập email → xong
    _reauth_tried = set()
    for _ch_try in range(4):
        _cur = page.url
        _on_myacc = "myaccount.google.com" in _cur and "challenge" not in _cur and "/v3/signin" not in _cur
        if _on_myacc:
            break
        await _bail_if_device_code(page, log_fn)   # dính thiết bị cũ → thoát ngay
        # NHANH: trang re-auth TOTP (challenge/totp) → điền mã 2FA CŨ NGAY, khỏi chạy các
        # handler recovery/password chậm (không áp dụng cho trang này) → tiết kiệm ~15s/kênh.
        _cl = _cur.lower()
        if (("challenge/totp" in _cl or "challenge/ipp" in _cl)
                and old_totp_secret and _valid_b32_secret(old_totp_secret)):
            _c = totp_now(old_totp_secret)
            if _c not in _reauth_tried:
                _reauth_tried.add(_c)
                _did = False
                for sel in ['input[type="tel"]', 'input[name="Pin"]',
                            'input[autocomplete="one-time-code"]', 'input[type="number"]']:
                    try:
                        inp = page.locator(sel)
                        if await inp.count() > 0 and await inp.first.is_visible():
                            try:
                                await inp.first.fill("")
                            except Exception:
                                pass
                            await inp.first.fill(_c)
                            log_fn(f"  ↩ Re-auth TOTP cũ (nhanh): {_c}")
                            if not await _click_by_text(page, _NEXT_TXT + _VERIFY_TXT, log_fn):
                                await _click_next(page)
                            _did = True
                            break
                    except Exception:
                        pass
                if _did:
                    await page.wait_for_timeout(2500)
                    continue
        log_fn(f"  [Challenge loop #{_ch_try+1}] URL={_cur[:80]}")
        await _handle_challenge_selection(page, password, recovery_email, log_fn)
        await _reauth_if_needed(page, password, log_fn)
        await page.wait_for_timeout(2500)
    await _skip_selfie_video(page, log_fn)
    log_fn(f"  [Challenge done] URL={page.url[:80]}")

    if (old_totp_secret and _valid_b32_secret(old_totp_secret)
            and ("challenge" in page.url or "signin" in page.url)):
        old_code = totp_now(old_totp_secret)
        for sel in ['input[type="tel"]', 'input[name="Pin"]',
                    'input[autocomplete="one-time-code"]', 'input[type="number"]']:
            try:
                inp = page.locator(sel)
                if await inp.count() > 0 and await inp.first.is_visible():
                    log_fn(f"  ↩ Re-auth TOTP cũ: {old_code}")
                    await inp.first.fill(old_code)
                    await _click_next(page)
                    await page.wait_for_timeout(3000)
                    break
            except Exception:
                pass
        await _reauth_if_needed(page, password, log_fn)

    await page.wait_for_timeout(1500)
    log_fn(f"  URL: {page.url[:80]}")
    # DEBUG: chụp ảnh sau khi navigate đến authenticator page
    try:
        await page.screenshot(path=_dbg_path("debug_auth_page.png"))
        _dbg_msg = f"[_nav_auth] URL={page.url}\n"
        with open(_dbg_path("debug_log.txt"), "a", encoding="utf-8") as _df:
            _df.write(_dbg_msg)
    except Exception as _e:
        log_fn(f"  [DEBUG] nav screenshot lỗi: {_e}")


def _on_full_myaccount(url: str) -> bool:
    """True nếu đang ở trang myaccount FULL (không phải bản rút gọn general-light)."""
    u = (url or "").lower()
    if "myaccount.google.com" not in u:
        return False
    return not any(bad in u for bad in ["general-light", "not-supported"])


async def _goto_twosv(page, password, recovery_email, log_fn, tries: int = 5) -> bool:
    """
    Đưa page tới trang 'Xác minh 2 bước' (twosv) BẢN FULL — trang có nút Authenticator.
    Chiến lược ổn định (tránh general-light/not-supported do điều hướng automation):
      1. Nếu đang ở general-light/not-supported/security → click link 'Xác minh 2 bước'
         (đây là điều hướng same-origin bằng cú click → Google trả bản full).
      2. Nếu chưa ở myaccount → điều hướng same-origin bằng JS (window.location).
      3. Xử lý challenge/re-auth nếu Google chèn giữa chừng.
    Trả về True nếu tìm thấy nút Authenticator / 'Bật tính năng Xác minh 2 bước'.
    """
    async def _has_2sv_controls() -> bool:
        try:
            n = await page.locator(
                'button:has-text("Authenticator"), a:has-text("Authenticator"), '
                '[role="button"]:has-text("Authenticator"), '
                'button:has-text("Bật tính năng Xác minh 2 bước"), '
                'button:has-text("Turn on 2-Step Verification")'
            ).count()
            return n > 0
        except Exception:
            return False

    for _t in range(tries):
        u = page.url or ""
        # Challenge / re-auth chen ngang
        if "challenge" in u or "/v3/signin" in u:
            await _bail_if_device_code(page, log_fn)   # dính thiết bị cũ → thoát ngay
            log_fn(f"  [twosv #{_t+1}] Challenge → xử lý re-auth")
            await _handle_challenge_selection(page, password, recovery_email, log_fn)
            await _reauth_if_needed(page, password, log_fn)
            await page.wait_for_timeout(2500)
            continue

        # Đã ở twosv và có control → xong
        if ("twosv" in u or "two-step" in u) and await _has_2sv_controls():
            log_fn(f"  [twosv] Đã ở trang 2 bước (full).")
            return True

        # Đang ở myaccount (kể cả general-light) → click link 'Xác minh 2 bước'
        clicked = False
        for txt in ["Xác minh 2 bước", "2-Step Verification"]:
            try:
                el = page.locator(
                    f'a:has-text("{txt}"), [role="link"]:has-text("{txt}"), '
                    f'div[role="button"]:has-text("{txt}")'
                )
                if await el.count() > 0 and await el.first.is_visible():
                    await el.first.click()
                    log_fn(f"  [twosv] Click '{txt}' (same-origin)")
                    await page.wait_for_timeout(3800)
                    clicked = True
                    break
            except Exception:
                pass
        if clicked:
            continue

        # Chưa ở myaccount → điều hướng same-origin bằng JS nếu đang trên google.com
        if "google.com" in u:
            try:
                await page.evaluate("(x) => { window.location.href = x; }", TWOSV_URL)
                log_fn("  [twosv] JS same-origin → twosv")
                await page.wait_for_timeout(3800)
                continue
            except Exception:
                pass

        # Fallback cuối: goto (có thể ra general-light; vòng sau sẽ click thoát)
        try:
            await page.goto(TWOSV_URL, wait_until="domcontentloaded", timeout=40000)
            await page.wait_for_timeout(3000)
        except Exception as _e:
            log_fn(f"  [twosv] goto lỗi: {_e}")
            await page.wait_for_timeout(1500)

    ok = await _has_2sv_controls()
    if not ok:
        log_fn(f"  [twosv] ⚠ Không tới được trang 2 bước full. URL={page.url[:90]}")
    return ok


async def _wait_for(page, check, timeout: int = 12000, interval: int = 700) -> bool:
    """Poll async check() cho tới khi truthy hoặc hết timeout (ms)."""
    import time as _t
    end = _t.time() + timeout / 1000.0
    while _t.time() < end:
        try:
            if await check():
                return True
        except Exception:
            pass
        await page.wait_for_timeout(interval)
    try:
        return bool(await check())
    except Exception:
        return False


async def _click_by_text(page, texts, log_fn=None, tag: str = "",
                         click_timeout: int = 4000) -> bool:
    """
    Click phần tử ĐANG HIỂN THỊ có text (button/a/role). Dùng click_timeout ngắn để
    KHÔNG treo 30s khi phần tử bị che. Trả True nếu click được.
    """
    for t in texts:
        for sel in [f'button:has-text("{t}")', f'a:has-text("{t}")',
                    f'[role="button"]:has-text("{t}")', f'[role="link"]:has-text("{t}")',
                    f'div[role="button"]:has-text("{t}")']:
            try:
                loc = page.locator(sel)
                n = await loc.count()
                for i in range(min(n, 5)):
                    el = loc.nth(i)
                    try:
                        if await el.is_visible():
                            await el.click(timeout=click_timeout)
                            if log_fn:
                                log_fn(f"  {tag}✓ Click '{t}'")
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
    return False


async def _open_authenticator_setup(page, log_fn) -> bool:
    """
    Từ trang twosv → vào trang 'Ứng dụng Authenticator' → bấm
    '+ Thiết lập ứng dụng xác thực' → chờ popup QR ('Không thể quét mã?').
    Khớp đúng flow thực tế của Google. Trả True nếu đã mở được popup QR.
    """
    async def _setup_btn_present():
        try:
            return await page.locator(
                'button:has-text("Thiết lập ứng dụng xác thực"), '
                'a:has-text("Thiết lập ứng dụng xác thực"), '
                '[role="button"]:has-text("Thiết lập ứng dụng xác thực")'
            ).count() > 0
        except Exception:
            return False

    # 1) Nếu chưa ở trang có nút 'Thiết lập…' → click hàng 'Authenticator' để vào
    if not await _setup_btn_present():
        await _click_by_text(page, _AUTH_ITEM_TXT, log_fn, tag="[auth] ")
        await _wait_for(page, _setup_btn_present, timeout=10000)

    # 2) Bấm '+ Thiết lập ứng dụng xác thực'.
    #    Nếu account đã có Authenticator (từ lần trước dở dang) → trang hiện
    #    'Thay đổi ứng dụng xác thực' → bấm nút này cũng mở popup secret.
    if not await _click_by_text(page, _CHANGE_AUTH_TXT, log_fn, tag="[auth] "):
        log_fn("  [auth] ⚠ Không thấy nút Thiết lập/Thay đổi ứng dụng xác thực")
        return False

    # 3) Chờ popup QR xuất hiện (có link 'Không thể quét mã?')
    async def _qr_ready():
        try:
            # popup mở nếu THẤY link 'Can't scan?' (đa ngôn ngữ) hoặc có QR (img/canvas)
            if not await _cant_scan_gone(page):
                return True
            return await page.locator(
                '[role="dialog"] img, [role="dialog"] canvas, '
                'img[src*="chart"], img[alt*="QR" i]'
            ).count() > 0
        except Exception:
            return False
    ok = await _wait_for(page, _qr_ready, timeout=12000)
    if ok:
        log_fn("  [auth] ✓ Popup QR đã mở")
    else:
        log_fn("  [auth] ⚠ Chưa thấy popup QR sau khi bấm Thiết lập")
    return True


async def _click_dialog_next(page, log_fn=None) -> bool:
    """Bấm nút 'Tiếp theo/Next' của hộp thoại — ĐỘC LẬP NGÔN NGỮ.
    B1: khớp text đa ngôn ngữ (_NEXT_TXT). B2 (nếu trượt): bấm nút KHẲNG ĐỊNH ở CUỐI (phải
    nhất) hộp thoại, TRÁNH Huỷ/Quay lại (_CANCEL_KW). Nhờ vậy account ngôn ngữ lạ (vd 下一页
    tiếng Trung giản thể chưa có trong danh sách) vẫn sang được bước nhập mã."""
    if await _click_in_frames(page, _NEXT_TXT, log_fn, tag="[ĐỔI 2FA] "):
        return True
    try:
        _frames = list(page.frames)
    except Exception:
        _frames = [page]
    for fr in _frames:
        try:
            btns = fr.locator('[role="dialog"] button, [role="dialog"] [role="button"], '
                              '[role="dialog"] a')
            n = await btns.count()
            for i in range(n - 1, -1, -1):        # từ nút PHẢI NHẤT (thường là Next) trở về
                el = btns.nth(i)
                try:
                    if not await el.is_visible():
                        continue
                    t = ((await el.inner_text()) or "").strip().lower()
                    if not t or any(c in t for c in _CANCEL_KW):
                        continue
                    if await _click_el(el):
                        if log_fn:
                            log_fn(f"  [ĐỔI 2FA] ✓ Sang bước sau (nút '{t[:20]}')")
                        return True
                except Exception:
                    pass
        except Exception:
            pass
    return False


async def _get_secret_from_popup(page, log_fn) -> str:
    """Click 'Không thể quét mã?' → đọc secret → click 'Tiếp theo'."""
    await page.wait_for_timeout(1500)
    # Guard: nếu đang ở trang rút gọn (general-light/not-supported) hoặc trang 404 thì
    # KHÔNG cố đọc secret (sẽ vớ nhầm chữ trong HTML -> secret rác -> crash base32).
    _u_low = (page.url or "").lower()
    if any(bad in _u_low for bad in ["general-light", "not-supported"]):
        log_fn(f"  ⚠ Trang rút gọn, không có QR/secret: {page.url[:80]}")
        return ""
    # DEBUG: chụp ảnh trang trước khi click để chẩn đoán (timeout ngắn, tránh treo 30s)
    try:
        await page.screenshot(path=_dbg_path("debug_before_cant_scan.png"), timeout=5000)
        _url_now = page.url
        log_fn(f"  [DEBUG] URL trước cant_scan: {_url_now[:120]}")
        _btns_before = [b.strip() for b in (await page.locator('button, a, [role="button"], span[jsname]').all_inner_texts()) if b.strip()][:20]
        log_fn(f"  [DEBUG] Buttons trước: {_btns_before}")
        with open(_dbg_path("debug_log.txt"), "a", encoding="utf-8") as _df:
            _df.write(f"[before_cant_scan] URL={_url_now}\nButtons={_btns_before}\n")
    except Exception as _de:
        log_fn(f"  [DEBUG] debug screenshot lỗi: {_de}")
    _before_url = page.url
    await _click_cant_scan(page, log_fn)
    # DEBUG: chụp ảnh SAU click cant_scan
    try:
        await page.screenshot(path=_dbg_path("debug_after_cant_scan.png"), timeout=5000)
        log_fn(f"  [DEBUG] URL sau cant_scan: {page.url[:120]}")
    except Exception:
        pass
    # Nếu click nhầm link → trang 404 / navigate away → quay lại
    if page.url != _before_url and "myaccount.google.com" not in page.url and "accounts.google.com" not in page.url:
        log_fn(f"  ⚠ Trang bị chuyển sang {page.url[:60]}, quay lại...")
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=10000)
            await page.wait_for_timeout(1500)
        except Exception:
            pass
    # Chờ mã bí mật hiện trong popup (Google cập nhật DOM bất đồng bộ sau khi bấm)
    secret = ""
    for _poll in range(12):
        secret = await _get_totp_secret_from_page(page, log_fn)
        if secret:
            break
        if _poll == 4:   # thử bấm lại 'Không thể quét mã?' nếu vẫn ở màn QR
            await _click_cant_scan(page, log_fn)
        await page.wait_for_timeout(800)

    if not secret:
        try:
            ss_path = _dbg_path("debug_2fa.png")
            await page.screenshot(path=ss_path)
            log_fn(f"  [DEBUG] Screenshot saved: {ss_path}")
        except Exception as _sse:
            log_fn(f"  [DEBUG] Screenshot FAILED: {_sse}")
        try:
            body = (await page.inner_text("body"))[:800]
            log_fn(f"  [DEBUG] URL lúc fail: {page.url[:120]}")
            log_fn(f"  [DEBUG] Body: {body[:600]}")
        except Exception as _be:
            log_fn(f"  [DEBUG] body lỗi: {_be}")
        return ""

    log_fn(f"  ✓ Secret: {secret[:8]}…")

    # Click "Tiếp theo" / "Next" để sang màn NHẬP MÃ. Dùng _click_dialog_next (độc lập ngôn
    # ngữ: khớp text, nếu trượt thì bấm nút cuối hộp thoại tránh Huỷ/Back) — xử lý được cả
    # account ngôn ngữ lạ. Thử lại 1 lần nếu lần đầu không ăn.
    if not await _click_dialog_next(page, log_fn):
        await page.wait_for_timeout(1200)
        await _click_dialog_next(page, log_fn)
    await page.wait_for_timeout(2000)

    return secret


class _DeviceCodeChallenge(Exception):
    """Google đòi 'Mã bảo mật' từ thiết bị đã đăng ký (dính thiết bị cũ) — KHÔNG tự động
    được. Raise để THOÁT NGAY mọi vòng lặp challenge, tránh treo luồng."""
    pass


async def _bail_if_device_code(page, log_fn) -> None:
    """Nếu đang ở trang device-code (đòi Mã bảo mật từ thiết bị) → raise để thoát luồng ngay."""
    try:
        if await _is_device_code_challenge(page):
            log_fn("  ⛔ DÍNH THIẾT BỊ CŨ (Google đòi Mã bảo mật từ thiết bị) → thoát luồng ngay, không quay vòng.")
            raise _DeviceCodeChallenge()
    except _DeviceCodeChallenge:
        raise
    except Exception:
        pass


async def _is_device_code_challenge(page) -> bool:
    """True nếu đang KẸT ở dạng 'Xác minh danh tính' đòi MÃ BẢO MẬT từ THIẾT BỊ đã đăng ký
    (điện thoại/máy tính bảng cũ). Dạng này KHÔNG tự động được (cần thiết bị vật lý để lấy mã).
    Dấu hiệu: URL challenge/ootp + có ô 'Nhập mã' + chữ 'mã bảo mật'/'xác minh danh tính'/
    'nhận ... của bạn' (đa ngôn ngữ)."""
    try:
        _u = (page.url or "").lower()
        url_hit = ("challenge/ootp" in _u) or ("challenge/az" in _u) or ("challenge/dp" in _u)
        body = ""
        try:
            body = (await page.inner_text("body"))[:4000].lower()
        except Exception:
            pass
        kw = ["mã bảo mật", "security code", "xác minh danh tính", "verify it",
              "verify your identity", "安全码", "安全性代碼", "보안 코드", "セキュリティ コード",
              "código de seguridad", "code de sécurité", "sicherheitscode", "kode keamanan",
              "код безопасности", "get a verification code", "nhận mã xác minh"]
        txt_hit = any(k in body for k in kw)
        # phải có ô nhập mã (để chắc là trang đòi nhập mã bảo mật, không phải trang khác)
        has_input = False
        try:
            has_input = await page.locator(
                'input[type="tel"], input[type="text"], input[aria-label*="mã" i], '
                'input[aria-label*="code" i]').first.is_visible()
        except Exception:
            pass
        # CHỈ coi là 'dính thiết bị cũ' khi URL ĐÚNG là trang device-code (challenge/ootp/az/dp)
        # + có ô nhập mã (hoặc chữ đặc trưng). KHÔNG dựa vào chữ đơn thuần — vì trang re-auth
        # 2FA bình thường (challenge/totp) cũng có tiêu đề 'Xác minh danh tính' + ô nhập mã,
        # dễ bị nhận nhầm → làm KÊNH NÀO cũng thoát sớm không đổi được 2FA.
        return url_hit and (txt_hit or has_input)
    except Exception:
        return False


async def do_create_2fa(ws_url: str, email: str, password: str,
                        recovery_email: str = "", log_fn=print) -> tuple[bool, str, str]:
    """
    Tao 2FA moi - flow theo huong dan:
    1. Login + xu ly challenge (recovery email)
    2. Xu ly trang post-login: Dam bao / Dat dia chi / Han che dich vu
    3. Navigate -> security page -> click Authenticator -> Thiet lap
    4. Lay secret -> nhap TOTP -> Xac minh
    """
    async with async_playwright() as p:
        log_fn("  [TAO 2FA] Ket noi browser...")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()

        await _navigate_to_authenticator_page(page, password, "", log_fn, recovery_email=recovery_email)

        # === XU LY CAC TRANG POST-LOGIN (toi da 8 lan) ===
        for _post_try in range(8):
            _u = page.url
            _txt = ""
            try:
                _txt = await page.inner_text("body")
            except Exception:
                pass
            log_fn(f"  [post #{_post_try+1}] URL={_u[:70]}")

            # Trang 'Đảm bảo…' → Huỷ ; trang 'Video selfie' → Để sau
            if await _skip_keep_signin_page(page, log_fn):
                continue
            if await _skip_selfie_video(page, log_fn):
                continue

            # Re-auth neu bi redirect ve challenge
            if "challenge" in _u or "/v3/signin" in _u:
                await _bail_if_device_code(page, log_fn)   # dính thiết bị cũ → thoát ngay
                log_fn("  [post] Re-auth challenge...")
                await _handle_challenge_selection(page, password, recovery_email, log_fn)
                await _reauth_if_needed(page, password, log_fn)
                await page.wait_for_timeout(2000)
                continue

            # Trang "Dam bao rang ban luon co the dang nhap" -> click Huy
            if ("dam bao" in _txt.lower() or
                    "luon co the dang nhap" in _txt.lower() or
                    "dam-bao" in _u or
                    "recovery/email" in _u or
                    "ensure" in _txt.lower()):
                log_fn("  [post] Trang Dam bao -> click Huy")
                _clicked = False
                for _t in ["Huỷ", "Cancel"]:
                    try:
                        _el = page.locator(f'button:has-text("{_t}"), a:has-text("{_t}")')
                        if await _el.count() > 0 and await _el.first.is_visible():
                            await _el.first.click()
                            await page.wait_for_timeout(2000)
                            _clicked = True
                            break
                    except Exception:
                        pass
                if not _clicked:
                    await page.go_back(timeout=10000)
                    await page.wait_for_timeout(2000)
                continue

            # Trang "Dat dia chi nha rieng" -> click Bo qua
            if ("dia chi nha rieng" in _txt.lower() or
                    "home address" in _txt.lower() or
                    "homeaddress" in _u):
                log_fn("  [post] Trang Dat dia chi -> click Bo qua")
                for _t in ["Bỏ qua", "Skip"]:
                    try:
                        _el = page.locator(f'a:has-text("{_t}"), button:has-text("{_t}")')
                        if await _el.count() > 0 and await _el.first.is_visible():
                            await _el.first.click()
                            await page.wait_for_timeout(2000)
                            break
                    except Exception:
                        pass
                continue

            # Trang "Xem han che ve dich vu" -> click avatar -> Quan ly Tai khoan Google
            if ("han chế" in _txt.lower() or
                    "servicerestrictedview" in _u or
                    "servicerestricted" in _u or
                    "service_restricted" in _u):
                log_fn("  [post] Trang Han che dich vu -> click avatar")
                try:
                    # Click account avatar (top right)
                    _av_sels = [
                        f'[aria-label*="{email}"]',
                        '[data-email]',
                        'a[href*="myaccount"] img',
                        '[aria-label*="Google Account"]',
                    ]
                    _av_clicked = False
                    for _avs in _av_sels:
                        try:
                            _av = page.locator(_avs)
                            if await _av.count() > 0:
                                await _av.first.click()
                                _av_clicked = True
                                await page.wait_for_timeout(1500)
                                break
                        except Exception:
                            pass
                    if not _av_clicked:
                        # fallback: navigate truc tiep
                        await page.goto("https://myaccount.google.com/security",
                                       wait_until="domcontentloaded", timeout=15000)
                        await page.wait_for_timeout(2000)
                        continue
                    # Click "Quan ly Tai khoan Google cua ban"
                    for _t in ["Quản lý Tài khoản Google của bạn",
                               "Manage your Google Account",
                               "Quản lý Tài khoản"]:
                        try:
                            _el = page.locator(f'a:has-text("{_t}"), button:has-text("{_t}")')
                            if await _el.count() > 0 and await _el.first.is_visible():
                                await _el.first.click()
                                await page.wait_for_timeout(3000)
                                break
                        except Exception:
                            pass
                except Exception as _e:
                    log_fn(f"  [post] avatar error: {_e}")
                    await page.goto("https://myaccount.google.com/security",
                                   wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(2000)
                continue

            # Da den myaccount.google.com -> thoat vong lap
            if ("myaccount.google.com" in _u and
                    "challenge" not in _u and
                    "/v3/signin" not in _u):
                log_fn(f"  [post] Da den myaccount OK")
                break

            await page.wait_for_timeout(1500)

        # === ĐẾN TRANG "XÁC MINH 2 BƯỚC" (twosv) — BẢN FULL có nút Authenticator ===
        # Không dùng page.goto("/security") vì điều hướng automation bị Google trả
        # general-light/not-supported. Dùng _goto_twosv: click link same-origin để lấy bản full.
        log_fn("  [TAO 2FA] Đến trang Xác minh 2 bước (twosv)…")
        on_twosv = await _goto_twosv(page, password, recovery_email, log_fn)
        try:
            await page.screenshot(path=_dbg_path("step_security.png"))
        except Exception:
            pass
        if not _on_full_myaccount(page.url):
            log_fn(f"  [TAO 2FA] ⚠ Vẫn ở bản rút gọn (general-light/not-supported): {page.url[:80]}")
            return False, "", ("Google trả trang rút gọn (không vào được trang 2FA). "
                               "Thường do fingerprint profile hỏng — kiểm tra User-Agent "
                               "profile GPM phải là Chrome thật, KHÔNG phải 'auto'.")
        if not on_twosv:
            log_fn("  [TAO 2FA] ⚠ Không thấy control 2 bước trên trang.")

        # === CLICK "Authenticator" → "Thiết lập ứng dụng xác thực" ===
        log_fn("  [TAO 2FA] Mở thiết lập Authenticator…")
        opened = await _open_authenticator_setup(page, log_fn)
        try:
            await page.screenshot(path=_dbg_path("step_before_qr.png"))
        except Exception:
            pass
        if not opened:
            _dev = await _is_device_code_challenge(page)
            if _dev:
                log_fn("  [TAO 2FA] ⛔ DÍNH THIẾT BỊ CŨ — Google đòi Mã bảo mật từ thiết bị "
                       "đã đăng ký. KHÔNG tự động được.")
                return False, "", ("DEVICE_CODE | DÍNH THIẾT BỊ CŨ — Google đòi 'Mã bảo mật' từ "
                                   "thiết bị đã đăng ký (điện thoại/máy tính bảng cũ). Không tự "
                                   "động được, phải duyệt tay bằng thiết bị đó.")
            return False, "", "Không mở được 'Thiết lập ứng dụng xác thực'"

        # === LAY SECRET (click "Khong the quet ma?" -> doc text key -> "Tiep theo") ===
        log_fn("  [TAO 2FA] Lay secret tu popup...")
        secret = await _get_secret_from_popup(page, log_fn)
        if not secret:
            return False, "", "Khong doc duoc secret key"

        # === LƯU NGAY secret ra FILE RECOVERY (QUAN TRỌNG, giống do_change_2fa) ===
        # Google có thể ĐÃ bật 2FA với secret này ngay cả khi bước sau lỗi → PHẢI lưu để
        # không mất account. Ghi bất kể kết quả xác minh.
        try:
            import os as _os_rec, datetime as _dt_rec
            _rec_path = _os_rec.path.join(_os_rec.path.dirname(_os_rec.path.abspath(__file__)),
                                          "2fa_recovery.txt")
            with open(_rec_path, "a", encoding="utf-8") as _rf:
                _rf.write(f"{_dt_rec.datetime.now():%Y-%m-%d %H:%M:%S}\t{email}\t{secret}\n")
            log_fn("  [TAO 2FA] 💾 Đã lưu secret vào 2fa_recovery.txt (phòng mất account)")
        except Exception as _rec_e:
            log_fn(f"  [TAO 2FA] ⚠ Không ghi được 2fa_recovery.txt: {_rec_e}")

        # === XAC MINH TOTP ===
        ok = await _verify_totp_and_confirm(page, secret, log_fn)
        # Dù verify báo gì, trang kế tiếp là 'Ứng dụng Authenticator' có nút 'Bật' —
        # LUÔN chạy bước bật 2 bước (không thoát sớm để tránh bỏ nút 'Bật').
        enabled = await _post_2fa_activate(page, log_fn)
        if enabled:
            return True, secret, "Tao 2FA thanh cong"
        if not ok:
            err = await _read_error_text(page)
            return False, secret, f"Ma 2FA co the sai / chua bat duoc 2 buoc: {err[:70]}"
        return True, secret, "Tao 2FA OK (chua xac nhan bat 2 buoc)"


async def do_change_2fa(ws_url: str, email: str, password: str,
                        old_totp_secret: str = "",
                        recovery_email: str = "",
                        log_fn=print) -> tuple[bool, str, str]:
    """
    Đổi 2FA cho tài khoản đã có Authenticator.
    Flow: Authenticator page → Thay đổi ứng dụng → Không thế quét mã? → Secret → Tiếp theo → Xác minh
    Trả về: (success, new_totp_secret, message)
    """
    async with async_playwright() as p:
        log_fn("  [ĐỔI 2FA] Kết nối browser…")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()

        # Dọn nudge còn sót sau login (Đảm bảo/selfie/địa chỉ nhà → Bỏ qua/Huỷ/Not now…)
        await _dismiss_post_login_prompts(page, log_fn, max_rounds=3)

        await _navigate_to_authenticator_page(page, password, old_totp_secret, log_fn, recovery_email=recovery_email)

        # === ĐẾN TRANG "XÁC MINH 2 BƯỚC" (twosv) BẢN FULL ===
        log_fn("  [ĐỔI 2FA] Đến trang Xác minh 2 bước (twosv)…")
        await _goto_twosv(page, password, recovery_email, log_fn)
        if not _on_full_myaccount(page.url):
            log_fn(f"  [ĐỔI 2FA] ⚠ Vẫn ở bản rút gọn: {page.url[:80]}")
            return False, "", ("Google trả trang rút gọn (không vào được trang 2FA). "
                               "Kiểm tra User-Agent profile GPM phải là Chrome thật, không phải 'auto'.")

        # === MỞ MỤC AUTHENTICATOR → CHỜ trang chi tiết (có 'Thay đổi'/'Thiết lập') ===
        await _click_in_frames(page, _AUTH_ITEM_TXT, log_fn, tag="[ĐỔI 2FA] ")

        # Sau khi bấm Authenticator, Google hay bắt XÁC MINH LẠI 2FA (challenge/totp)
        # trước khi cho đổi → nhập lại mã 2FA cũ. Nút đa ngôn ngữ: Tiếp theo/Next/Xác minh/Verify.
        # Mã TOTP đổi mỗi 30s và Google VÔ HIỆU mã ngay khi đã dùng 1 lần → mỗi lần thử
        # PHẢI dùng mã MỚI (khác các lần trước). Nếu mã hiện tại đã thử → CHỜ sang chu
        # kỳ 30s mới. Ô nhập được XÓA trước khi điền để tránh nối chuỗi.
        # Hàm: nếu đang ở trang challenge (Google bắt xác minh LẠI 2FA cũ trước khi cho đổi)
        # → nhập lại mã 2FA cũ (mã MỚI mỗi lần, chờ chu kỳ 30s mới nếu trùng). Gọi được
        # NHIỀU LẦN vì Google có khi bắt xác minh lại NGAY TRƯỚC nút 'Thay đổi'.
        _reauth_tried = set()
        async def _reauth_challenge(rounds=6):
            for _ra in range(rounds):
                await page.wait_for_timeout(1200)
                _u = page.url.lower()
                if _is_logged_in(page.url) or not ("challenge" in _u or "/signin/" in _u):
                    return
                if not _valid_b32_secret(old_totp_secret):
                    return
                _code = totp_now(old_totp_secret)
                _waited = 0
                while _code in _reauth_tried and _waited < 35:
                    if _waited == 0:
                        log_fn("  [ĐỔI 2FA] Mã cũ hết hạn/đã dùng → chờ mã TOTP mới…")
                    await page.wait_for_timeout(2000)
                    _waited += 2
                    _code = totp_now(old_totp_secret)
                _reauth_tried.add(_code)
                _filled = False
                for _s in ['input[type="tel"]', 'input[name="Pin"]',
                           'input[autocomplete="one-time-code"]',
                           'input[aria-label*="code" i]', 'input[aria-label*="mã" i]',
                           'input[type="number"]']:
                    try:
                        _inp = page.locator(_s)
                        if await _inp.count() > 0 and await _inp.first.is_visible():
                            try:
                                await _inp.first.fill("")   # xóa mã cũ còn trong ô
                            except Exception:
                                pass
                            await _inp.first.fill(_code)
                            _filled = True
                            break
                    except Exception:
                        pass
                if not _filled:
                    return
                log_fn(f"  [ĐỔI 2FA] Xác minh lại 2FA cũ: {_code}")
                if not await _click_by_text(page, _NEXT_TXT + _VERIFY_TXT, log_fn):
                    await _click_next(page)
                await page.wait_for_timeout(3500)

        await _reauth_challenge()

        async def _change_present() -> bool:
            for fr in page.frames:
                try:
                    if await fr.locator(
                        'a:has-text("Thay đổi"), button:has-text("Thay đổi"), '
                        '[role="button"]:has-text("Thay đổi"), '
                        'a:has-text("Change authenticator"), '
                        'a:has-text("Thiết lập ứng dụng xác thực"), '
                        'button:has-text("Thiết lập ứng dụng xác thực"), '
                        'a:has-text("更改"), button:has-text("更改"), '
                        '[role="button"]:has-text("更改"), '
                        'a:has-text("變更"), button:has-text("變更")').count() > 0:
                        return True
                except Exception:
                    pass
            return False
        await _wait_for(page, _change_present, timeout=12000)

        # === CLICK "Thay đổi ứng dụng xác thực" — quét mọi frame + JS-click (ĐA NGÔN NGỮ) ===
        change_clicked = await _click_in_frames(page, _CHANGE_AUTH_TXT,
                                                log_fn, tag="[ĐỔI 2FA] ")
        if change_clicked:
            await page.wait_for_timeout(2500)
        else:
            log_fn("  [ĐỔI 2FA] ⚠ Không thấy 'Thay đổi' → thử 'Thiết lập'…")
            try:
                await page.screenshot(path=_dbg_path("debug_change.png"))
                _seen = []
                for _fr in page.frames:
                    try:
                        _seen += [t.strip() for t in await _fr.locator(
                            'button, a, [role="button"]').all_inner_texts() if t.strip()]
                    except Exception:
                        pass
                log_fn(f"  [ĐỔI 2FA] URL={page.url[:80]} | Nút thấy: {_seen[:30]}")
            except Exception:
                pass
            # Google có khi bắt XÁC MINH LẠI 2FA cũ NGAY TRƯỚC nút 'Thay đổi' (trang
            # challenge/totp). → xác minh lại rồi thử tìm nút Thay đổi LẦN NỮA.
            _u2 = page.url.lower()
            if "challenge" in _u2 or "/signin/" in _u2:
                log_fn("  [ĐỔI 2FA] Trang challenge trước nút Thay đổi → xác minh lại 2FA cũ rồi thử lại…")
                await _reauth_challenge()
                await _wait_for(page, _change_present, timeout=10000)
                change_clicked = await _click_in_frames(page, _CHANGE_AUTH_TXT,
                                                        log_fn, tag="[ĐỔI 2FA] ")
            if change_clicked:
                await page.wait_for_timeout(2500)
            else:
                opened = await _open_authenticator_setup(page, log_fn)
                if not opened:
                    if await _is_device_code_challenge(page):
                        log_fn("  [ĐỔI 2FA] ⛔ DÍNH THIẾT BỊ CŨ — Google đòi Mã bảo mật từ thiết bị đã đăng ký.")
                        return False, "", ("DEVICE_CODE | DÍNH THIẾT BỊ CŨ — Google đòi 'Mã bảo mật' "
                                           "từ thiết bị đã đăng ký (điện thoại/máy tính bảng cũ). "
                                           "Không tự động được, phải duyệt tay bằng thiết bị đó.")
                    return False, "", "Không tìm thấy nút Thay đổi/Thiết lập ứng dụng xác thực"

        # === CHỜ POPUP QR + LẤY SECRET MỚI ===
        new_secret = await _get_secret_from_popup(page, log_fn)
        if not new_secret:
            return False, "", "Không đọc được secret 2FA mới"

        # === LƯU NGAY secret mới ra FILE RECOVERY (QUAN TRỌNG) ===
        # Google có thể ĐÃ đổi sang secret mới NGAY khi hiện mã, dù bước xác minh sau đó
        # tool báo lỗi. Nếu không lưu → account dính 2FA mới mà ta KHÔNG biết mã → mất account.
        # → Ghi full secret + email + thời gian ra file để LUÔN khôi phục được, bất kể kết quả.
        try:
            import os as _os_rec, datetime as _dt_rec
            _rec_path = _os_rec.path.join(_os_rec.path.dirname(_os_rec.path.abspath(__file__)),
                                          "2fa_recovery.txt")
            with open(_rec_path, "a", encoding="utf-8") as _rf:
                _rf.write(f"{_dt_rec.datetime.now():%Y-%m-%d %H:%M:%S}\t{email}\t{new_secret}\n")
            log_fn(f"  [ĐỔI 2FA] 💾 Đã lưu secret mới vào 2fa_recovery.txt (phòng mất account)")
        except Exception as _rec_e:
            log_fn(f"  [ĐỔI 2FA] ⚠ Không ghi được 2fa_recovery.txt: {_rec_e}")

        # === XÁC MINH MÃ MỚI (2 bước đã bật sẵn → không cần bấm 'Bật') ===
        ok = await _verify_totp_and_confirm(page, new_secret, log_fn)
        await page.wait_for_timeout(2000)
        # Bỏ qua popup 'Xong'/'Bỏ qua' nếu có sau khi đổi
        await _click_in_frames(page, ["Bỏ qua", "Skip"], log_fn, tag="[ĐỔI 2FA] ")
        await _click_in_frames(page, ["Xong", "Done"], log_fn, tag="[ĐỔI 2FA] ")
        log_fn("  [ĐỔI 2FA] Đợi 5s trước khi kết thúc…")
        await page.wait_for_timeout(5000)
        if ok:
            log_fn(f"  [ĐỔI 2FA] ✅ Đổi 2FA OK — secret MỚI: {new_secret}")
            return True, new_secret, "Đổi 2FA thành công"
        err = await _read_error_text(page)
        return False, new_secret, f"Xác minh mã mới thất bại: {err[:80]}"


# ══════════════════════════════════════════════════════════════════
#  KÊNH YOUTUBE — lấy link kênh / tạo kênh khi chưa có
# ══════════════════════════════════════════════════════════════════
import re as _re_ch


async def _extract_channel_id(page) -> str:
    """Lấy channel ID của TÀI KHOẢN ĐANG ĐĂNG NHẬP (UC + 22 ký tự).
    CHỈ tin 2 nguồn CHẮC CHẮN, KHÔNG quét UC trong HTML thô — vì trang YouTube
    chứa rất nhiều UC-id lạ (kênh gợi ý, video nhúng…) → account CHƯA có kênh
    dễ bị bắt nhầm 1 UC-id lạ thành link kênh sai.
      1) URL .../channel/UCxxxx (Studio/YouTube tự redirect khi CÓ kênh).
      2) ytcfg CHANNEL_ID — chính là kênh của user đang đăng nhập (rỗng nếu chưa có kênh)."""
    # 1) từ URL
    try:
        m = _re_ch.search(r'/channel/(UC[0-9A-Za-z_-]{22})', page.url or "")
        if m:
            return m.group(1)
    except Exception:
        pass
    # 2) từ ytcfg CHANNEL_ID của chính user (không phải UC trong nội dung trang)
    try:
        cid = await page.evaluate(
            """() => {
                try {
                    if (window.ytcfg) {
                        if (ytcfg.get) { const v = ytcfg.get('CHANNEL_ID'); if (v) return v; }
                        if (ytcfg.data_ && ytcfg.data_.CHANNEL_ID) return ytcfg.data_.CHANNEL_ID;
                    }
                } catch (e) {}
                return "";
            }"""
        )
        if cid and _re_ch.match(r'^UC[0-9A-Za-z_-]{22}$', cid):
            return cid
    except Exception:
        pass
    return ""


# Dấu hiệu kênh/tài khoản YouTube bị KHÓA / CHẤM DỨT (die)
_DEAD_CHANNEL_KEYS = (
    "has been terminated", "account has been terminated",
    "channel has been terminated", "has been suspended",
    "account isn't available", "account is not available",
    "channel isn't available", "isn't available",
    "no longer available", "this channel doesn't exist",
    "this channel does not exist", "terminated for a violation",
    "community guidelines",
    "đã bị chấm dứt", "đã bị tạm ngưng", "đã bị đình chỉ", "đã bị khóa",
    "đã bị khoá", "không khả dụng", "không còn khả dụng",
    "kênh này không tồn tại", "tài khoản này đã bị",
    "vi phạm nguyên tắc cộng đồng",
)


async def _channel_dead_reason(page) -> str:
    """Trả về cụm text nếu kênh/tài khoản bị khóa/chấm dứt (die); ngược lại ''."""
    try:
        for fr in page.frames:
            try:
                t = _norm_txt(await fr.inner_text("body"))[:5000]
            except Exception:
                continue
            for k in _DEAD_CHANNEL_KEYS:
                if k in t:
                    return k
    except Exception:
        pass
    return ""


async def _click_create_channel_href(page, log_fn) -> bool:
    """Bấm phần tử 'Tạo kênh' theo LINK create_channel (không phụ thuộc ngôn ngữ)."""
    for fr in page.frames:
        for sel in ('a[href*="create_channel"]',
                    '[href*="create_channel"]',
                    'a[href*="/channel_creation"]'):
            try:
                loc = fr.locator(sel)
                if await loc.count() > 0 and await loc.first.is_visible():
                    if await _click_el(loc.first):
                        log_fn("  [KÊNH] ✓ Mở tạo kênh (link create_channel)")
                        await page.wait_for_timeout(3500)
                        return True
            except Exception:
                pass
    return False


# Nút 'Tạo kênh' — CHỈ dùng cụm ĐẦY ĐỦ có chữ 'kênh/channel', KHÔNG dùng từ 'Tạo/Create'
# đơn lẻ (dễ khớp nhầm nút '+ Tạo' ở góc phải để tạo video). Đa ngôn ngữ theo locale account.
_CREATE_CH_NAMES = [
    "TẠO KÊNH", "Tạo kênh", "Tạo một kênh",
    "CREATE CHANNEL", "Create channel", "Create a channel",
    "चैनल बनाएं", "चैनल बनाएँ",                          # Hindi
    "채널 만들기",                                        # Korean
    "创建频道", "建立頻道",                              # zh
    "チャンネルを作成",                                  # Japanese
    "Crear canal", "Criar canal", "Créer une chaîne",   # es/pt/fr
    "Kanal erstellen", "Buat channel", "Buat saluran",  # de/id/ms
    "Создать канал", "إنشاء قناة", "قناة جديدة",        # ru/ar
    "สร้างช่อง", "চ্যানেল তৈরি করুন",                    # th/bn
    "ಚಾನಲ್ ರಚಿಸಿ",                                       # Kannada
    "चॅनल तयार करा", "ચેનલ બનાવો", "ചാനൽ സൃഷ്ടിക്കുക",   # mr/gu/ml
    "చానెల్‌ని క్రియేట్ చేయండి",                          # te
    "Kanal oluştur",                                    # tr
]


async def _click_dialog_primary_create(page, log_fn) -> bool:
    """Bấm nút TẠO (nút chính) trong hộp thoại 'How you'll appear' — KHÔNG phụ thuộc
    ngôn ngữ. Hộp thoại có 2 nút (Huỷ + Tạo); nút Tạo là nút CUỐI/bên phải."""
    for sel in ('tp-yt-paper-dialog', 'ytcp-dialog', 'yt-confirm-dialog-renderer',
                '[role="dialog"]', 'ytd-modal-with-title-and-button-renderer'):
        for fr in page.frames:
            try:
                dlg = fr.locator(sel)
                if await dlg.count() == 0:
                    continue
                btns = dlg.first.locator(
                    'button, ytcp-button, tp-yt-paper-button, yt-button-shape, [role="button"]')
                nb = await btns.count()
                for i in range(nb - 1, -1, -1):   # nút cuối thường là 'Tạo'
                    b = btns.nth(i)
                    try:
                        if await b.is_visible() and await _click_el(b):
                            log_fn("  [KÊNH] ✓ Bấm nút Tạo (nút chính trong hộp thoại)")
                            await page.wait_for_timeout(3500)
                            return True
                    except Exception:
                        pass
            except Exception:
                pass
    return False


import random as _rnd_ch


async def _channel_create_blocked(page) -> bool:
    """Google CHẶN tạo kênh vì đã nhập quá nhiều tên/handle (khoá ~24h). Phát hiện để
    KHÔNG thử lại (thử lại chỉ làm bị khoá lâu hơn)."""
    keys = ("quá nhiều tên không dùng được", "hãy thử lại sau 24", "thử lại sau 24 giờ",
            "too many", "try again in 24", "try again later", "24 hours", "24 giờ")
    for fr in page.frames:
        try:
            body = (await fr.locator("body").inner_text()) or ""
        except Exception:
            body = ""
        bl = body.lower()
        if any(k in bl for k in keys):
            return True
    return False


_ALNUM_CH = "abcdefghijklmnopqrstuvwxyz0123456789"


def _rand_chars(k: int) -> str:
    return "".join(_rnd_ch.choice(_ALNUM_CH) for _ in range(k))


def _is_handle_field(_h, _val) -> bool:
    return ("@" in _h or "@" in _val or "sebutan" in _h or "handle" in _h
            or "người dùng" in _h or "username" in _h)


_CH_FIELD_SEL = ('input[type="text"], input:not([type]), '
                 'tp-yt-paper-input input, ytcp-social-suggestions-textbox input')


async def _get_ch_field(page, want_handle: bool):
    """Trả (element, value_hiện_tại) của ô Tên (want_handle=False) / Handle (True)."""
    for fr in page.frames:
        try:
            inputs = fr.locator(_CH_FIELD_SEL); n = await inputs.count()
        except Exception:
            continue
        for i in range(min(n, 12)):
            el = inputs.nth(i)
            try:
                if not await el.is_visible():
                    continue
                _h = (((await el.get_attribute("placeholder")) or "") + " " +
                      ((await el.get_attribute("aria-label")) or "")).lower()
                _val = (await el.input_value()) or ""
                if _is_handle_field(_h, _val) == want_handle:
                    return el, _val
            except Exception:
                pass
    return None, ""


async def _set_ch_field(page, want_handle: bool, value: str, log_fn, label: str) -> bool:
    el, _ = await _get_ch_field(page, want_handle)
    if el is None:
        return False
    try:
        await el.click()
        try:
            await el.fill("")
        except Exception:
            pass
        await el.fill(value)
        log_fn(f"  [KÊNH] {label}: {value}")
        await page.wait_for_timeout(900)
        return True
    except Exception:
        return False


async def _channel_field_error(page) -> str:
    """Trả cụm lỗi ĐỎ nếu Tên/Handle CHƯA hợp lệ; '' nếu hợp lệ (tick xanh, hết đỏ)."""
    errs = ("can't be used", "cannot be used", "không dùng được", "không thể dùng",
            "unavailable", "not available", "đã được sử dụng", "already taken",
            "already in use", "not valid", "invalid", "không hợp lệ",
            "try a different", "thử lại với", "chọn tên khác", "different name")
    for fr in page.frames:
        try:
            body = (await fr.locator("body").inner_text()).lower()
        except Exception:
            body = ""
        for e in errs:
            if e in body:
                return e
    return ""


async def _fill_channel_name(page, chname, chandle, log_fn):
    """Điền Tên + Handle rồi CHỈNH đến khi hợp lệ (hết báo đỏ / handle tick xanh):
      - Ban đầu: Tên = chname (TỐI ĐA 15 ký tự); Handle = (YouTube đề xuất) + 5 ký tự random.
      - Mỗi vòng chưa hợp lệ: Tên xóa 3 ký tự cuối + thêm 6 ký tự random (giữ ≤15);
        Handle xóa 3 ký tự cuối + thêm 3 ký tự random. Tối đa 5 vòng.
    Trả: True (hợp lệ) / False (5 vòng vẫn lỗi) / 'BLOCKED' (Google khoá 24h)."""
    # điền Tên ban đầu (≤15 ký tự)
    await _set_ch_field(page, False, (chname or "user")[:15], log_fn, "Điền tên kênh")
    await page.wait_for_timeout(1800)   # chờ YouTube tự đề xuất handle
    # Handle = đề xuất của YouTube + 5 ký tự random
    _el, hsug = await _get_ch_field(page, True)
    hbase = (hsug or "").strip().lstrip("@") or chandle
    await _set_ch_field(page, True, (hbase + _rand_chars(5))[:29], log_fn,
                        "Handle = đề xuất + 5 random")
    await page.wait_for_timeout(1600)

    for attempt in range(5):
        if await _channel_create_blocked(page):
            return "BLOCKED"
        err = await _channel_field_error(page)
        if not err:
            log_fn(f"  [KÊNH] ✓ Tên/handle hợp lệ (lần {attempt + 1})")
            return True
        log_fn(f"  [KÊNH] ⚠ Chưa hợp lệ ({err}) → chỉnh Tên(-3+6,≤15)/Handle(-3+3) {attempt + 1}/5")
        # Tên: xóa 3 ký tự cuối + thêm 6 random, cắt còn ≤15
        _e, cur_name = await _get_ch_field(page, False)
        base_n = cur_name[:-3] if len(cur_name) > 3 else (cur_name or "u")
        await _set_ch_field(page, False, (base_n + _rand_chars(6))[:15], log_fn, "Sửa tên")
        # Handle: xóa 3 ký tự cuối + thêm 3 random
        _e2, cur_h = await _get_ch_field(page, True)
        cur_h = (cur_h or "").strip().lstrip("@")
        base_h = cur_h[:-3] if len(cur_h) > 3 else (cur_h or "u")
        await _set_ch_field(page, True, (base_h + _rand_chars(3))[:29], log_fn, "Sửa handle")
        await page.wait_for_timeout(1800)
    return not await _channel_field_error(page)


async def _create_channel_default(page, log_fn, email: str = "") -> bool:
    """Tạo kênh mặc định (tên = TÊN MAIL + 5 số random). Xử lý ĐA NGÔN NGỮ + link create_channel.
    Luồng: channel_switcher → 'Tạo kênh' → hộp thoại 'How you'll appear' → ĐIỀN TÊN
    → bấm nút xác nhận tạo → chờ redirect /channel/UCxxxx."""
    # TÊN + HANDLE sinh MỘT LẦN — KHÔNG đổi mỗi lần thử (đổi nhiều lần → Google chặn
    # 'nhập quá nhiều tên không dùng được' → khoá 24h). Thêm số random cho khỏi trùng.
    uname = (email or "").split("@")[0].strip() or "user"
    chname = (uname[:9] + _rand_chars(6))[:15]     # TÊN ≤ 15 ký tự (9 tên + 6 random)
    chandle = (uname + _rand_chars(4))[:28]        # handle dự phòng nếu không đọc được đề xuất

    try:
        await page.goto("https://www.youtube.com/channel_switcher",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception:
        pass
    if await _extract_channel_id(page):
        return True

    # 1) Mở hộp thoại tạo kênh (link create_channel ưu tiên, rồi nút tên đầy đủ)
    opened = await _click_create_channel_href(page, log_fn)
    if not opened:
        opened = await _click_in_frames(page, _CREATE_CH_NAMES, log_fn, tag="[KÊNH] ")
    await page.wait_for_timeout(2500)
    if await _extract_channel_id(page):
        return True

    # 2) Điền + CHỈNH Tên(≤15)/Handle đến khi hợp lệ (hàm tự lặp tối đa 5 lần).
    res = await _fill_channel_name(page, chname, chandle, log_fn)
    if res == "BLOCKED":
        log_fn("  [KÊNH] ✗ Google chặn tạo kênh: nhập quá nhiều tên → thử lại sau 24h")
        return False
    if res is False:
        # có thể chưa mở được hộp thoại → mở lại 1 lần rồi điền lại
        opened = await _click_create_channel_href(page, log_fn)
        if not opened:
            await _click_in_frames(page, _CREATE_CH_NAMES, log_fn, tag="[KÊNH] ")
        await page.wait_for_timeout(2500)
        if await _extract_channel_id(page):
            return True
        res = await _fill_channel_name(page, chname, chandle, log_fn)
        if res == "BLOCKED":
            log_fn("  [KÊNH] ✗ Google chặn tạo kênh: nhập quá nhiều tên → thử lại sau 24h")
            return False

    await page.wait_for_timeout(1200)

    # 4) Bấm nút Tạo — chỉ thử lại thao tác BẤM (KHÔNG đổi tên), tối đa 3 lần.
    for _try in range(3):
        if await _click_dialog_primary_create(page, log_fn):
            pass
        else:
            await _click_in_frames(page, _CREATE_CH_NAMES, log_fn, tag="[KÊNH] ")
        await page.wait_for_timeout(3500)
        if await _extract_channel_id(page):
            return True
        if await _channel_create_blocked(page):
            log_fn("  [KÊNH] ✗ Google chặn tạo kênh: đã nhập quá nhiều tên → thử lại sau 24h")
            return False

    # 5) Chưa xong → chụp debug để xem trạng thái
    try:
        await page.screenshot(path=_dbg_path("debug_channel.png"), timeout=5000)
        _seen = []
        for _fr in page.frames:
            try:
                _seen += [t.strip() for t in await _fr.locator(
                    'button, a, [role="button"], ytcp-button, tp-yt-paper-button'
                ).all_inner_texts() if t.strip()]
            except Exception:
                pass
        log_fn(f"  [KÊNH] URL={page.url[:70]} | Nút thấy: {_seen[:25]}")
    except Exception:
        pass
    return False


async def _resolve_handle_to_ucid(page, handle: str) -> str:
    """Mở trang @handle → lấy UC id (canonical / channelId của chính trang kênh đó)."""
    try:
        await page.goto(f"https://www.youtube.com/{handle}",
                        wait_until="domcontentloaded", timeout=25000)
        await page.wait_for_timeout(2000)
    except Exception:
        pass
    try:
        canon = await page.locator('link[rel="canonical"]').first.get_attribute('href')
        m = _re_ch.search(r'/channel/(UC[0-9A-Za-z_-]{22})', canon or "")
        if m:
            return m.group(1)
    except Exception:
        pass
    try:
        cid = await page.evaluate(
            """() => {
                const h = document.documentElement.innerHTML;
                let m = h.match(/"channelId":"(UC[0-9A-Za-z_-]{22})"/)
                     || h.match(/\\/channel\\/(UC[0-9A-Za-z_-]{22})/);
                return m ? m[1] : "";
            }"""
        )
        if cid:
            return cid
    except Exception:
        pass
    return ""


async def _find_existing_channel_id(page, log_fn) -> str:
    """Vào 'Tất cả kênh' (channel_switcher) để xem account CÓ SẴN kênh nào không —
    KỂ CẢ brand channel dù identity đang active chưa có kênh cá nhân.
    Trả UC id kênh đầu tiên tìm được; '' nếu account thật sự chưa có kênh nào.
    Mục đích: TRÁNH tạo kênh mới trùng khi account đã có kênh."""
    try:
        await page.goto("https://www.youtube.com/channel_switcher",
                        wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
    except Exception:
        pass
    # a) link /channel/UC trực tiếp
    for fr in page.frames:
        try:
            loc = fr.locator('a[href*="/channel/UC"], [href*="/channel/UC"]')
            n = await loc.count()
            for i in range(min(n, 15)):
                href = await loc.nth(i).get_attribute("href") or ""
                m = _re_ch.search(r'/channel/(UC[0-9A-Za-z_-]{22})', href)
                if m:
                    log_fn(f"  [KÊNH] Tìm thấy kênh sẵn có: {m.group(1)}")
                    return m.group(1)
        except Exception:
            pass
    # b) Quét ytInitialData (channel_switcher CHỈ chứa kênh của chính account → an toàn)
    #    Đây là nguồn chắc chắn nhất khi account item render bằng custom element (không có <a href>).
    try:
        cids = await page.evaluate(
            """() => {
                try {
                    const s = JSON.stringify(window.ytInitialData || {});
                    const set = new Set(); const re = /"(UC[0-9A-Za-z_-]{22})"/g; let m;
                    while ((m = re.exec(s))) set.add(m[1]);
                    return [...set];
                } catch (e) { return []; }
            }"""
        )
        for c in (cids or []):
            if _re_ch.match(r'^UC[0-9A-Za-z_-]{22}$', c):
                log_fn(f"  [KÊNH] Kênh sẵn có (ytInitialData): {c}")
                return c
    except Exception:
        pass
    # c) @handle từ TEXT hiển thị (vd '@阿允_QsIZ') — account item không có <a href>
    handles = []
    try:
        _body = await page.inner_text("body")
        for _h in _re_ch.findall(r'(@[^\s@/\\?&#"\']{2,40})', _body):
            _h = _h.rstrip('.,):;')
            if _h and _h not in handles:
                handles.append(_h)
    except Exception:
        pass
    # d) @handle từ href (nếu có)
    for fr in page.frames:
        try:
            loc = fr.locator('a[href*="/@"]')
            n = await loc.count()
            for i in range(min(n, 15)):
                href = await loc.nth(i).get_attribute("href") or ""
                m = _re_ch.search(r'/(@[^/?&#"\']+)', href)
                if m and m.group(1) not in handles:
                    handles.append(m.group(1))
        except Exception:
            pass
    for h in handles[:6]:
        cid = await _resolve_handle_to_ucid(page, h)
        if cid:
            log_fn(f"  [KÊNH] Kênh sẵn có qua handle {h}: {cid}")
            return cid
    return ""


async def do_channel(ws_url: str, email: str = "", create_if_missing: bool = True,
                     log_fn=print) -> tuple[bool, str, str]:
    """
    Lấy link kênh YouTube (LUÔN dạng https://www.youtube.com/channel/UCxxxx).
    - Đã có kênh → trả link.
    - Chưa có kênh và create_if_missing=True → tạo kênh mới (tên mặc định Google) → trả link.
    - Chưa có kênh và create_if_missing=False → báo 'chưa có kênh'.
    Trả về: (success, channel_url, message)
    """
    async with async_playwright() as p:
        log_fn("  [KÊNH] Kết nối browser…")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = await ctx.new_page()

        # Dọn nudge còn sót sau login
        await _dismiss_post_login_prompts(page, log_fn, max_rounds=2)

        # 1) Vào YouTube Studio — tự redirect /channel/UCxxxx nếu đã có kênh,
        #    hoặc hiện hộp thoại tạo kênh nếu chưa có.
        log_fn("  [KÊNH] Mở YouTube Studio…")
        try:
            await page.goto("https://studio.youtube.com",
                            wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            log_fn(f"  [KÊNH] ⚠ Mở Studio chậm: {str(e)[:50]}")
        # chờ redirect / settle
        for _ in range(6):
            await page.wait_for_timeout(2000)
            if "/channel/UC" in (page.url or ""):
                break

        cid = await _extract_channel_id(page)
        if cid:
            url = f"https://www.youtube.com/channel/{cid}"
            log_fn(f"  [KÊNH] ✓ Đã có kênh: {url}")
            log_fn("  [KÊNH] Đợi 5s trước khi sang nhiệm vụ khác…")
            await page.wait_for_timeout(5000)
            return True, url, "Đã có kênh"

        # 2a) KÊNH DIE — kênh/tài khoản bị khóa hoặc chấm dứt (không vào lấy link được)
        dead = await _channel_dead_reason(page)
        if dead:
            log_fn(f"  [KÊNH] ✗ KÊNH DIE (dấu hiệu: '{dead}')")
            return False, "KÊNH DIE", f"KÊNH DIE | Kênh/tài khoản bị khóa hoặc chấm dứt ({dead})"

        # 2b) Identity đang active chưa có kênh, NHƯNG account có thể có BRAND channel.
        #     Kiểm tra 'Tất cả kênh' — nếu ĐÃ có kênh thì lấy link đó, TUYỆT ĐỐI không tạo mới.
        log_fn("  [KÊNH] Kiểm tra 'Tất cả kênh' (tránh tạo trùng)…")
        existing = await _find_existing_channel_id(page, log_fn)
        if existing:
            url = f"https://www.youtube.com/channel/{existing}"
            log_fn(f"  [KÊNH] ✓ Account ĐÃ CÓ kênh (kể cả brand): {url} — KHÔNG tạo mới")
            log_fn("  [KÊNH] Đợi 5s trước khi sang nhiệm vụ khác…")
            await page.wait_for_timeout(5000)
            return True, url, "Đã có kênh"

        # 2c) Thật sự chưa có kênh nào
        if not create_if_missing:
            log_fn("  [KÊNH] ⚠ Chưa có kênh (chỉ lấy link, không tạo)")
            return False, "", "Chưa có kênh"

        log_fn("  [KÊNH] Chưa có kênh → tạo kênh mới (tên = mail + 5 số random)…")
        created = await _create_channel_default(page, log_fn, email)
        if not created:
            dead = await _channel_dead_reason(page)
            if dead:
                log_fn(f"  [KÊNH] ✗ KÊNH DIE (dấu hiệu: '{dead}')")
                return False, "KÊNH DIE", f"KÊNH DIE | Kênh/tài khoản bị khóa hoặc chấm dứt ({dead})"
            return False, "", "Không tạo được kênh (không thấy nút Tạo kênh/Create channel)"

        # 3) Lấy channel id sau khi tạo
        cid = ""
        for _ in range(8):
            cid = await _extract_channel_id(page)
            if cid:
                break
            await page.wait_for_timeout(2500)
        if not cid:
            return False, "", "Đã tạo kênh nhưng chưa lấy được channel ID"
        url = f"https://www.youtube.com/channel/{cid}"
        log_fn(f"  [KÊNH] ✅ Tạo kênh xong: {url}")
        log_fn("  [KÊNH] Đợi 5s trước khi sang nhiệm vụ khác…")
        await page.wait_for_timeout(5000)
        return True, url, "Đã tạo kênh mới"


def _pick_random_banner(banner_dir: str) -> str:
    """Chọn NGẪU NHIÊN 1 file ảnh trong thư mục ảnh bìa."""
    import os as _os, random as _rd
    try:
        exts = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
        files = [_os.path.join(banner_dir, f) for f in _os.listdir(banner_dir)
                 if f.lower().endswith(exts)]
        return _rd.choice(files) if files else ""
    except Exception:
        return ""


async def _dismiss_studio_popups(page, log_fn=None) -> None:
    """Đóng các popup Studio hay chen ngang: 'Welcome to YouTube Studio' (Continue),
    'Got it', 'Dismiss', 'Close', 'Skip', 'No thanks'… (đa ngôn ngữ)."""
    txts = ["Continue", "Got it", "No thanks", "Dismiss", "Skip", "Not now",
            "Tiếp tục", "Đã hiểu", "Bỏ qua", "Đóng", "Để sau",
            "ต่อไป", "ดำเนินการต่อ", "รับทราบ", "ปิด",
            "继续", "繼續", "知道了", "確定", "확인", "계속", "続行", "了解"]
    for _round in range(3):
        _clicked = False
        for t in txts:
            try:
                loc = page.locator(f'ytcp-button:has-text("{t}"), button:has-text("{t}"), '
                                   f'tp-yt-paper-button:has-text("{t}"), '
                                   f'[role="button"]:has-text("{t}"), a:has-text("{t}")')
                n = await loc.count()
                for i in range(min(n, 4)):
                    el = loc.nth(i)
                    try:
                        if await el.is_visible():
                            await el.click(timeout=2500)
                            if log_fn:
                                log_fn(f"  [BÌA] ✓ Đóng popup: '{t}'")
                            _clicked = True
                            await page.wait_for_timeout(1000)
                            break
                    except Exception:
                        pass
                if _clicked:
                    break
            except Exception:
                pass
        if not _clicked:
            break
        await page.wait_for_timeout(700)


async def _brand_channel_id_via_switcher(page, current_cid: str, log_fn) -> str:
    """Lấy channel ID kênh THỨ 2 (brand) qua trang THẬT youtube.com/channel_switcher.
    KHÔNG click menu/avatar (hay bị backdrop chặn + timeout) → chắc & nhanh.
    Trả '' nếu chỉ có 1 kênh; trả id kênh brand nếu tìm được."""
    try:
        await page.goto("https://www.youtube.com/channel_switcher",
                        wait_until="domcontentloaded", timeout=40000)
    except Exception:
        return ""

    # CHỜ danh sách kênh RENDER (SPA) — trước đây đọc ngay sau domcontentloaded nên
    # luôn chỉ thấy 1 kênh. Trang này là trang THẬT (không backdrop) → bấm được an toàn.
    _item_sels = ['ytd-account-item-renderer',
                  'ytd-account-section-list-renderer a[href]',
                  '#contents a[href*="/channel/"]']
    items = None
    for _ in range(12):
        await page.wait_for_timeout(1000)
        for s in _item_sels:
            try:
                loc = page.locator(s)
                if await loc.count() >= 2:
                    items = loc
                    break
            except Exception:
                pass
        if items is not None:
            break

    if items is not None:
        try:
            n = await items.count()
            log_fn(f"  [BÌA] channel_switcher: {n} kênh → chọn kênh thứ 2")
            await items.nth(1).click(timeout=5000, force=True)
            await page.wait_for_timeout(3000)
            await page.goto("https://studio.youtube.com/?hl=en",
                            wait_until="domcontentloaded", timeout=40000)
            await page.wait_for_timeout(3000)
            m = __import__("re").search(r'/channel/(UC[0-9A-Za-z_-]{22})', page.url or "")
            _cid2 = m.group(1) if m else (await _extract_channel_id(page))
            if _cid2 and _cid2 != current_cid:
                return _cid2
        except Exception:
            pass

    ids = []
    try:
        # CHỈ lấy ID ở vị trí CÓ CẤU TRÚC. (Quét cả HTML bằng /UC.{22}/ sẽ bắt NHẦM
        # token/base64 ngẫu nhiên → từng cho ra '7 kênh' rác và chọn sai kênh.)
        ids = await page.evaluate("""() => {
            const html = document.documentElement.innerHTML;
            const out = [];
            const push = id => { if (id && out.indexOf(id) === -1) out.push(id); };
            const pats = [
                /"channelId"\\s*:\\s*"(UC[0-9A-Za-z_-]{22})"/g,
                /"browseId"\\s*:\\s*"(UC[0-9A-Za-z_-]{22})"/g,
                /\\/channel\\/(UC[0-9A-Za-z_-]{22})/g
            ];
            for (const re of pats) {
                let m;
                while ((m = re.exec(html)) !== null) push(m[1]);
            }
            return out;
        }""")
    except Exception:
        ids = []
    ids = [i for i in (ids or []) if i]
    log_fn(f"  [BÌA] channel_switcher thấy {len(ids)} kênh: {', '.join(ids[:6])}")
    if not ids:
        return ""
    if len(ids) > 6:
        log_fn(f"  [BÌA] ⚠ Số kênh bất thường ({len(ids)}) — bỏ qua kết quả này để tránh chọn sai.")
        return ""
    # Kênh brand = kênh KHÁC kênh hiện tại. Nếu chưa biết kênh hiện tại → lấy kênh thứ 2.
    if current_cid:
        others = [i for i in ids if i != current_cid]
        return others[0] if others else ""
    return ids[1] if len(ids) >= 2 else ""


async def _switch_to_second_channel(page, log_fn) -> str:
    """Chuyển sang kênh THỨ 2 (brand) qua: avatar (góc phải) → 'Switch account' → chọn kênh
    THỨ 2 trong danh sách. Cách này CHẮC CHẮN hơn hộp 'Select a channel' hiện chập chờn.
    Trả channel_id kênh brand sau khi chuyển (rỗng nếu chỉ 1 kênh / không chuyển được)."""
    import re as __re
    def _cid_of(u):
        m = __re.search(r'/channel/(UC[0-9A-Za-z_-]{22})', u or "")
        return m.group(1) if m else ""

    async def _dismiss_backdrop():
        """Đóng backdrop/overlay đang chặn click (tp-yt-iron-overlay-backdrop) — nếu không
        sẽ bị retry click 30s = ĐỨNG LÂU."""
        try:
            bd = page.locator('tp-yt-iron-overlay-backdrop.opened, tp-yt-iron-overlay-backdrop[opened]')
            if await bd.count() > 0:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(400)
        except Exception:
            pass

    async def _fclick(loc, timeout_ms=2500) -> bool:
        """Click FORCE (bỏ qua backdrop-intercept) timeout NGẮN → không treo."""
        try:
            await loc.click(timeout=timeout_ms, force=True)
            return True
        except Exception:
            return False

    try:
        # 0) Chờ Studio vào 1 dashboard (tối đa ~14s). Hộp 'Select a channel' → bấm kênh ĐẦU để vào.
        for _ in range(14):
            if "/channel/UC" in (page.url or ""):
                break
            try:
                it0 = page.locator('ytcp-account-item-renderer, ytd-account-item-renderer, '
                                   '[role="dialog"] a[href*="/channel/"], '
                                   'tp-yt-paper-dialog tp-yt-paper-item')
                if await it0.count() >= 1 and await it0.first.is_visible():
                    await _fclick(it0.first)
                    await page.wait_for_timeout(2000)
            except Exception:
                pass
            await page.wait_for_timeout(700)

        _before = _cid_of(page.url)
        log_fn(f"  [BÌA] Đang ở kênh {_before or '?'} → chuyển sang kênh thứ 2 (Switch account)…")

        # 1) Mở menu avatar (Studio dùng #avatar-btn; timeout ngắn)
        for s in ['#avatar-btn', 'button#avatar-btn', 'ytcp-icon-button#avatar-btn',
                  '#masthead #avatar-btn', '#account-button button', '#account-button']:
            try:
                el = page.locator(s)
                if await el.count() > 0 and await el.first.is_visible():
                    await _fclick(el.first)
                    await page.wait_for_timeout(1300)
                    break
            except Exception:
                pass

        # 2) Bấm 'Switch account' (đa ngôn ngữ) — force click, timeout ngắn
        _sw_txt = ["Switch account", "Chuyển đổi tài khoản", "Chuyển tài khoản",
                   "สลับบัญชี", "切換帳戶", "切换账号", "계정 전환", "アカウントを切り替え"]
        for t in _sw_txt:
            try:
                sw = page.locator(f'ytcp-account-item-renderer:has-text("{t}"), '
                                  f'tp-yt-paper-item:has-text("{t}"), '
                                  f'a:has-text("{t}"), [role="button"]:has-text("{t}"), '
                                  f'div:has-text("{t}")')
                n = await sw.count()
                _hit = False
                for i in range(min(n, 6)):
                    e = sw.nth(i)
                    try:
                        if await e.is_visible() and await _fclick(e):
                            log_fn(f"  [BÌA] ✓ Bấm '{t}'")
                            _hit = True
                            break
                    except Exception:
                        pass
                if _hit:
                    await page.wait_for_timeout(2200)
                    break
            except Exception:
                pass

        # 3) Danh sách kênh → click kênh THỨ 2 (brand). Force click; xác nhận cid ĐÃ ĐỔI.
        for sel in ['ytcp-account-item-renderer',
                    'ytd-account-item-renderer',
                    '[role="dialog"] a[href*="/channel/"]',
                    'tp-yt-paper-dialog tp-yt-paper-item',
                    'a#account-item']:
            try:
                loc = page.locator(sel)
                if await loc.count() >= 2 and await loc.nth(1).is_visible():
                    await _dismiss_backdrop()
                    if not await _fclick(loc.nth(1), timeout_ms=3500):
                        continue
                    for _ in range(8):
                        await page.wait_for_timeout(1500)
                        _now = _cid_of(page.url)
                        if _now and _now != _before:
                            log_fn(f"  [BÌA] ✓ Đã chuyển sang kênh thứ 2: {_now}")
                            return _now
                    # cid chưa đổi trong URL → ép vào Studio dashboard đọc lại cid
                    try:
                        await page.goto("https://studio.youtube.com/?hl=en",
                                        wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(2500)
                        _now = _cid_of(page.url) or await _extract_channel_id(page)
                        if _now and _now != _before:
                            log_fn(f"  [BÌA] ✓ Đã chuyển sang kênh thứ 2: {_now}")
                            return _now
                    except Exception:
                        pass
            except Exception:
                pass

        # Không chuyển được → debug. PHÂN BIỆT: có ≥2 kênh mà fail (→ 'FAIL', caller báo lỗi,
        # KHÔNG đổi nhầm kênh đầu) vs chỉ 1 kênh (→ '', caller dùng kênh hiện tại).
        _n_items = 0
        try:
            await page.screenshot(path=_dbg_path("debug_select_channel.png"), timeout=5000)
            _diag = {}
            for s in ['ytcp-account-item-renderer', 'ytd-account-item-renderer',
                      '#avatar-btn', '[role="dialog"]', 'a[href*="/channel/"]']:
                try:
                    _diag[s] = await page.locator(s).count()
                except Exception:
                    _diag[s] = -1
            _n_items = max(_diag.get('ytcp-account-item-renderer', 0),
                           _diag.get('ytd-account-item-renderer', 0))
            log_fn(f"  [BÌA] ⚠ Chưa chuyển được kênh thứ 2. url={ (page.url or '')[:55] } "
                   f"counts={_diag}. Xem debug_select_channel.png")
        except Exception:
            pass
        return "FAIL" if _n_items >= 2 else ""
    except Exception:
        return ""


async def _set_youtube_language_english(page, log_fn) -> bool:
    """Đổi NGÔN NGỮ tài khoản YouTube sang English (US) QUA UI (lưu server-side →
    Studio kế thừa). Nhận diện mục 'Language' KHÔNG DỰA VÀO CHỮ (chạy với mọi ngôn
    ngữ) và TUYỆT ĐỐI không bấm nhầm 'Sign out' (chỉ bấm mục CÀI ĐẶT có dòng phụ).
    Có timeout ở mọi bước → không treo. Trả True nếu đã đặt English."""
    # (1) Mở youtube.com
    try:
        await page.goto("https://www.youtube.com/", wait_until="domcontentloaded", timeout=40000)
        await page.wait_for_timeout(2500)
    except Exception:
        pass

    # Helper: tìm option 'English (US)/(UK)/English' đang hiện trong submenu
    async def _english_option():
        for t in ["English (US)", "English (United States)", "English (UK)",
                  "English (United Kingdom)", "English"]:
            try:
                opt = page.locator(
                    f'tp-yt-paper-item:has-text("{t}"), a:has-text("{t}"), '
                    f'yt-formatted-string:has-text("{t}")')
                n = await opt.count()
                for i in range(min(n, 12)):
                    el = opt.nth(i)
                    try:
                        if await el.is_visible():
                            return el
                    except Exception:
                        pass
            except Exception:
                pass
        return None

    async def _click_back():
        try:
            bk = page.locator('#back-button, tp-yt-paper-icon-button#back-button, '
                              'ytd-multi-page-menu-renderer #back-button')
            if await bk.count() > 0 and await bk.first.is_visible():
                await bk.first.click(timeout=2500)
                await page.wait_for_timeout(600)
        except Exception:
            pass

    # (2) Mở menu avatar (ID cố định, không phụ thuộc ngôn ngữ)
    try:
        av = page.locator('#avatar-btn')
        if await av.count() == 0 or not await av.first.is_visible():
            av = page.locator('button#avatar-btn, ytd-topbar-menu-button-renderer button')
        if await av.count() == 0:
            log_fn("  [LANG] Không thấy avatar (chưa đăng nhập?) — bỏ qua đổi ngôn ngữ.")
            return False
        # force=True: bỏ qua kiểm tra bị-che (backdrop) → không treo/timeout như trước
        await av.first.click(timeout=4000, force=True)
        await page.wait_for_timeout(1300)
    except Exception as e:
        log_fn(f"  [LANG] Không mở được menu avatar: {e}")
        return False

    # (3) Nếu account đang tiếng Anh sẵn: có thể đã có 'Language' text — thử nhanh
    for t in ["Language", "ภาษา", "언어", "语言", "語言", "言語", "Idioma", "Langue",
              "Sprache", "Ngôn ngữ", "Idioma", "Язык", "Bahasa", "Ngôn ngữ"]:
        try:
            it = page.locator(f'ytd-compact-link-renderer:has-text("{t}")')
            if await it.count() > 0 and await it.first.is_visible():
                await it.first.click(timeout=3500)
                await page.wait_for_timeout(1000)
                opt = await _english_option()
                if opt is not None:
                    await opt.click(timeout=4000)
                    await page.wait_for_timeout(2500)
                    log_fn("  [LANG] ✓ Đã đổi ngôn ngữ sang English (US).")
                    return True
                await _click_back()
                break
        except Exception:
            pass

    # (4) Cách CHẮC NHẤT (mọi ngôn ngữ): duyệt các mục CÀI ĐẶT có DÒNG PHỤ (subtitle) —
    #     chỉ Appearance/Language/Location/Restricted có subtitle; nav-item & Sign out KHÔNG.
    #     Mục nào mở ra list chứa 'English' → đó là Ngôn ngữ → chọn English.
    try:
        items = page.locator('ytd-compact-link-renderer')
        total = await items.count()
    except Exception:
        total = 0
    for i in range(min(total, 15)):
        try:
            it = items.nth(i)
            if not await it.is_visible():
                continue
            sub = it.locator('#subtitle, yt-formatted-string#subtitle')
            has_sub = False
            try:
                has_sub = (await sub.count() > 0) and bool((await sub.first.inner_text()).strip())
            except Exception:
                has_sub = False
            if not has_sub:
                continue   # bỏ qua nav-item / Sign out (không có dòng phụ) → AN TOÀN
            await it.click(timeout=3500)
            await page.wait_for_timeout(900)
            opt = await _english_option()
            if opt is not None:
                await opt.click(timeout=4000)
                await page.wait_for_timeout(2500)
                log_fn("  [LANG] ✓ Đã đổi ngôn ngữ sang English (US).")
                return True
            await _click_back()   # không phải Ngôn ngữ → quay lại thử mục kế
        except Exception:
            await _click_back()
    log_fn("  [LANG] ⚠ Không đổi được ngôn ngữ qua menu (tiếp tục với URL hl=en).")
    return False


async def do_leave_admin(ws_url: str, email: str = "", password: str = "",
                         log_fn=print) -> tuple[bool, str, str]:
    """THOÁT QUẢN TRỊ kênh (brand): tự gỡ tài khoản khỏi Brand Account của kênh thứ 2.
    Theo đúng 7 bước:
      1) mở myaccount.google.com/brandaccounts
      2) click brand account trong 'Your Brand Accounts'
      3) click 'Manage Permissions'
      4) nếu bị hỏi lại mật khẩu → nhập lại → 5) click 'Manage Permissions' lần nữa
      6) trong hộp → dòng CHÍNH MÌNH (role Owner, KHÔNG phải Primary owner) → bấm X
      7) hộp 'Remove user' → REMOVE
    Xác minh: mở lại /brandaccounts, mục 'Your Brand Accounts' KHÔNG còn kênh → thành công.
    KHÔNG bao giờ bấm 'Delete account'/'Primary owner'. Trả (success, '', message)."""
    async with async_playwright() as p:
        log_fn("  [QT] Kết nối browser…")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        # ÉP TIẾNG ANH: để nút xoá có aria-label 'Remove …' (KHÔNG phải 'Xóa …' dễ trùng
        # 'Xóa tài khoản/Delete account'), và hộp xác nhận là 'Remove yourself'.
        try:
            await ctx.add_cookies([
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".google.com", "path": "/"},
            ])
        except Exception:
            pass
        page = await ctx.new_page()

        import re as __re

        async def _brand_ids_on_page() -> set:
            """Lấy ID brand từ TOÀN BỘ HTML trang hiện tại (KHÔNG chỉ thẻ <a>). Các dòng brand
            trên myaccount là list-item JS (không có href) → phải quét HTML/data. ID brand là
            /brandaccounts/<≥10 số> hoặc obfuscatedGaiaId dạng số dài; loại path chữ như
            'emailpreferences'/'deleted'."""
            try:
                html = await page.content()
            except Exception:
                return set()
            ids = set()
            # href brand là TƯƠNG ĐỐI: href="brandaccounts/<id>/view" (KHÔNG có '/' đầu)
            # → KHÔNG ràng buộc dấu '/' đầu.
            ids |= set(__re.findall(r'brandaccounts/(\d{10,})', html))
            # nguồn tin cậy thứ 2: data-id="<id số dài>" trên chính dòng brand
            for m in __re.findall(r'data-id="(\d{15,})"', html):
                if (f'brandaccounts/{m}' in html) or ('data-id="%s"' % m in html):
                    ids.add(m)
            return ids

        async def _read_brand_ids(navigate: bool = True) -> tuple[bool, set]:
            """Mở trang brandaccounts & đọc ID brand. Trả (loaded_ok, set_ids).
              - (False, set())  = KHÔNG load được trang (mạng/chưa đăng nhập) → KHÔNG kết luận 0.
              - (True,  set())  = load OK nhưng THẬT SỰ 0 brand (đã chờ đủ lâu).
              - (True,  {ids})  = có brand.
            Chờ TỚI KHI có id brand (tối đa ~15s). Nếu vẫn 0 → LƯU HTML+ảnh debug để soi."""
            if navigate:
                try:
                    await page.goto("https://myaccount.google.com/brandaccounts?pli=1&hl=en",
                                    wait_until="domcontentloaded", timeout=40000)
                except Exception:
                    return False, set()
            on_page = False
            for _ in range(15):
                await page.wait_for_timeout(1000)
                if "brandaccounts" in (page.url or ""):
                    on_page = True
                    ids = await _brand_ids_on_page()
                    if ids:
                        await page.wait_for_timeout(1200)      # ổn định
                        ids = await _brand_ids_on_page() or ids
                        return True, ids
                    # HẾT BRAND THẬT SỰ: trang đã render (có mục 'Deleted accounts' —
                    # luôn hiển thị) NHƯNG không còn mục 'Your Brand Accounts'
                    # → kết luận NGAY 0 brand, không chờ hết 15s, không lưu debug.
                    try:
                        _rendered = await page.get_by_text(
                            __re.compile("Deleted accounts", __re.I)).count() > 0
                        _has_sec = await page.get_by_text(
                            __re.compile("Your Brand Accounts", __re.I)).count() > 0
                        if _rendered and not _has_sec:
                            return True, set()
                    except Exception:
                        pass
            # trang mở nhưng sau ~15s KHÔNG thấy id brand → LƯU DEBUG rồi coi là 0
            if on_page:
                try:
                    _h = await page.content()
                    with open(_dbg_path("debug_brandaccounts.html"), "w",
                              encoding="utf-8") as _f:
                        _f.write(_h)
                    await page.screenshot(path=_dbg_path("debug_brandaccounts.png"), timeout=5000)
                    log_fn("  [QT] (đã lưu debug_brandaccounts.html + .png để kiểm tra)")
                except Exception:
                    pass
            return on_page, set()

        # ── B1+B2: mở trang & đọc danh sách brand ───────────────────────────
        log_fn("  [QT] Mở trang Brand Accounts…")
        _ok0, _ids0 = await _read_brand_ids()
        if not _ok0:
            return False, "", "Không mở được trang Brand Accounts (mạng/chưa đăng nhập?)"
        n0 = len(_ids0)
        if n0 <= 0:
            log_fn("  [QT] Account KHÔNG có brand account nào (không có kênh brand để thoát).")
            return False, "", "Không có Brand Account nào để thoát quản trị"
        log_fn(f"  [QT] Có {n0} brand → sẽ thoát quản trị TẤT CẢ.")

        # ── Helper dùng chung cho từng brand ────────────────────────────────
        async def _click_manage() -> bool:
            for t in ["Manage permissions", "Manage Permissions"]:
                try:
                    b = page.locator(f'button:has-text("{t}"), a:has-text("{t}"), '
                                     f'[role="button"]:has-text("{t}")')
                    n = await b.count()
                    for i in range(min(n, 4)):
                        e = b.nth(i)
                        if await e.is_visible():
                            await e.click(timeout=5000)
                            return True
                except Exception:
                    pass
            return False

        async def _leave_one(target_id: str) -> tuple[bool, str]:
            """Gỡ CHÍNH MÌNH khỏi 1 brand (theo id). Trả (ok, message)."""
            _detail_url = (f"https://myaccount.google.com/brandaccounts/"
                           f"{target_id}/view?hl=en")

            async def _dialog_open() -> bool:
                try:
                    return await page.get_by_text(
                        __re.compile("Primary owner", __re.I)).count() > 0
                except Exception:
                    return False

            async def _open_perms_dialog() -> tuple[bool, str]:
                """Mở hộp Manage permissions. XỬ LÝ: Google đá sang màn nhập lại mật khẩu
                (có thể load chậm) và sau re-auth bị trả về trang DANH SÁCH thay vì details.
                → mỗi vòng: về đúng trang details, bấm nút, rồi DÒ 15s cho 3 khả năng."""
                for _att in range(3):
                    # 1) đảm bảo đang ở đúng trang details của brand này
                    if f"/brandaccounts/{target_id}" not in (page.url or ""):
                        try:
                            await page.goto(_detail_url,
                                            wait_until="domcontentloaded", timeout=40000)
                            await page.wait_for_timeout(2500)
                        except Exception:
                            continue
                    if await _dialog_open():
                        return True, ""
                    # 2) bấm Manage Permissions; nếu KHÔNG có nút (trang biến thể) → mở THẲNG
                    #    URL trang permissions (một số brand account không render nút Manage).
                    if not await _click_manage():
                        try:
                            _perms_url = (f"https://myaccount.google.com/brandaccounts/"
                                          f"{target_id}/permissions?hl=en")
                            await page.goto(_perms_url,
                                            wait_until="domcontentloaded", timeout=40000)
                            await page.wait_for_timeout(2500)
                        except Exception:
                            pass
                        if await _dialog_open():
                            return True, ""
                        # vẫn chưa mở → thử lại vòng ngoài
                        await page.wait_for_timeout(1000)
                        continue
                    # 3) DÒ tối đa 15s: hộp mở? / hỏi mật khẩu? / bị đá đi chỗ khác?
                    _need_retry = False
                    for _ in range(15):
                        await page.wait_for_timeout(1000)
                        if await _dialog_open():
                            return True, ""
                        try:
                            _has_pw = await page.locator(
                                'input[type="password"]').count() > 0
                        except Exception:
                            _has_pw = False
                        if _has_pw:
                            if not password:
                                return False, "Bị hỏi lại mật khẩu nhưng không có mật khẩu"
                            log_fn("  [QT] Google hỏi lại mật khẩu → nhập lại…")
                            await _reauth_if_needed(page, password, log_fn)
                            await page.wait_for_timeout(3000)
                            try:
                                if await page.locator(
                                        'input[type="password"]').count() > 0:
                                    return False, "Nhập lại mật khẩu không qua (sai mật khẩu?)"
                            except Exception:
                                pass
                            _need_retry = True   # về details & bấm lại ở vòng ngoài
                            break
                    if _need_retry:
                        continue
                return False, "Không mở được hộp Manage permissions"

            _okd, _msgd = await _open_perms_dialog()
            if not _okd:
                try:
                    await page.screenshot(path=_dbg_path("debug_leave_admin.png"), timeout=5000)
                except Exception:
                    pass
                return False, _msgd

            # Bấm nút Remove của DÒNG CHÍNH MÌNH; gate REMOVE bằng hộp 'Remove yourself'.
            _removed = False
            _dlg = page.locator('div[role="dialog"], tp-yt-paper-dialog, c-wiz')
            _scope = _dlg.last if await _dlg.count() > 0 else page
            _cands = _scope.locator(
                'button[aria-label*="Remove" i], [role="button"][aria-label*="Remove" i]')
            try:
                n = await _cands.count()
                for i in range(min(n, 6)):
                    e = _cands.nth(i)
                    try:
                        _al = (await e.get_attribute("aria-label") or "").lower()
                        if any(bad in _al for bad in ["add", "invite", "member",
                                                      "delete", "account"]):
                            continue
                        if not await e.is_visible():
                            continue
                        await e.click(timeout=4000)
                        await page.wait_for_timeout(1500)
                        _has_confirm = False
                        for _cf in [r"Remove yourself", r"Remove user"]:
                            try:
                                if await page.get_by_text(__re.compile(_cf, __re.I)).count() > 0:
                                    _has_confirm = True
                                    break
                            except Exception:
                                pass
                        if _has_confirm and await _click_by_text(
                                page, ["REMOVE", "Remove"], log_fn, tag="[QT] "):
                            _removed = True
                            break
                        try:
                            await page.keyboard.press("Escape")
                            await page.wait_for_timeout(600)
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                pass

            if not _removed:
                try:
                    await page.screenshot(path=_dbg_path("debug_leave_admin.png"), timeout=5000)
                except Exception:
                    pass
                return False, "Không bấm được Remove/REMOVE để tự gỡ"
            await page.wait_for_timeout(3000)

            # Xác minh brand NÀY đã biến mất
            _okv, _ids_after = await _read_brand_ids()
            if not _okv:
                return False, "Đã REMOVE nhưng không mở lại được trang để xác minh"
            if target_id not in _ids_after:
                return True, "ok"
            return False, "Brand vẫn còn trong danh sách sau khi REMOVE"

        # ── LẶP qua TẤT CẢ brand ────────────────────────────────────────────
        _done, _fail = [], []
        for _bid in sorted(_ids0):
            log_fn(f"  [QT] → Thoát quản trị brand {_bid}…")
            ok1, msg1 = await _leave_one(_bid)
            if ok1:
                _done.append(_bid)
                log_fn(f"  [QT] ✅ Đã thoát brand {_bid}.")
            else:
                _fail.append(_bid)
                log_fn(f"  [QT] ⚠ Brand {_bid} chưa gỡ được: {msg1}")

        # Xác minh tổng: đọc lại danh sách còn lại
        _okL, _left = await _read_brand_ids()
        if _okL and not _left:
            log_fn(f"  [QT] ✅ Đã thoát quản trị TẤT CẢ {len(_done)} brand.")
            return True, "", f"Đã thoát quản trị tất cả {len(_done)} kênh brand"
        # Còn sót brand → thất bại (báo rõ còn cái nào)
        log_fn(f"  [QT] ⚠ Còn {len(_left)} brand chưa gỡ: {', '.join(list(_left)[:4])}")
        return False, "", (f"Gỡ được {len(_done)}/{n0} brand; CÒN {len(_left)} chưa gỡ "
                           f"(xem debug_leave_admin.png)")


async def _list_channel_ids(page, log_fn=None) -> list:
    """Đọc DANH SÁCH kênh của tài khoản qua trang THẬT youtube.com/channel_switcher.
    ĐẾM theo ITEM KÊNH trên DOM (trang liệt kê kênh bằng @handle, KHÔNG phải 'channelId:UC…'
    nên moi UC ID sẽ thiếu). Trả list có ĐỘ DÀI = SỐ KÊNH; phần tử là UC id thật khi có,
    còn lại là @handle — đủ để đếm & so với kênh chính."""
    try:
        import time as _t_cb
        await page.goto(f"https://www.youtube.com/channel_switcher?hl=en&_t={int(_t_cb.time())}",
                        wait_until="domcontentloaded", timeout=40000)
    except Exception:
        return []
    data = {"ids": [], "handles": [], "count": 0}
    for _ in range(14):
        await page.wait_for_timeout(1000)
        try:
            data = await page.evaluate(r"""() => {
                const html = document.documentElement.innerHTML;
                // UC id thật (nếu có)
                const ids = [];
                const push = id => { if (id && ids.indexOf(id) === -1) ids.push(id); };
                [/"channelId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"/g,
                 /"externalId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"/g,
                 /"browseId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"/g,
                 /\/channel\/(UC[0-9A-Za-z_-]{22})/g
                ].forEach(re => { let m; while ((m = re.exec(html)) !== null) push(m[1]); });
                // ĐẾM item kênh trên DOM
                let cnt = 0;
                ['ytd-account-item-renderer','yt-account-item-renderer',
                 'ytd-account-section-list-renderer ytd-compact-link-renderer'
                ].forEach(s => { const n = document.querySelectorAll(s).length; if (n > cnt) cnt = n; });
                // @handle (link /@... ) — mỗi kênh 1 handle
                const hs = new Set();
                document.querySelectorAll('a[href^="/@"]').forEach(a => {
                    const h = (a.getAttribute('href')||'').split('?')[0];
                    if (h && h.length > 1) hs.add(h);
                });
                const handles = Array.from(hs);
                const count = Math.max(cnt, handles.length, ids.length);
                return {ids: ids, handles: handles, count: count};
            }""")
        except Exception:
            data = {"ids": [], "handles": [], "count": 0}
        if (data.get("count") or 0) >= 1:
            await page.wait_for_timeout(1200)   # ổn định nếu kênh thứ 2 render trễ
            try:
                d2 = await page.evaluate(r"""() => {
                    const html = document.documentElement.innerHTML;
                    const ids = [];
                    const push = id => { if (id && ids.indexOf(id) === -1) ids.push(id); };
                    [/"channelId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"/g,
                     /"externalId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"/g,
                     /"browseId"\s*:\s*"(UC[0-9A-Za-z_-]{22})"/g,
                     /\/channel\/(UC[0-9A-Za-z_-]{22})/g
                    ].forEach(re => { let m; while ((m = re.exec(html)) !== null) push(m[1]); });
                    let cnt = 0;
                    ['ytd-account-item-renderer','yt-account-item-renderer',
                     'ytd-account-section-list-renderer ytd-compact-link-renderer'
                    ].forEach(s => { const n = document.querySelectorAll(s).length; if (n>cnt) cnt=n; });
                    const hs = new Set();
                    document.querySelectorAll('a[href^="/@"]').forEach(a => {
                        const h = (a.getAttribute('href')||'').split('?')[0];
                        if (h && h.length > 1) hs.add(h);
                    });
                    const handles = Array.from(hs);
                    return {ids: ids, handles: handles, count: Math.max(cnt, handles.length, ids.length)};
                }""")
                if d2 and (d2.get("count") or 0) >= (data.get("count") or 0):
                    data = d2
            except Exception:
                pass
            break
    ids = list(dict.fromkeys([i for i in (data.get("ids") or []) if i]))
    handles = [h for h in (data.get("handles") or []) if h]
    count = int(data.get("count") or 0)
    if count > 10:   # nhiễu bất thường
        if log_fn:
            log_fn(f"  [ADDQT] ⚠ Số kênh bất thường ({count}) — bỏ để tránh nhầm.")
        return []
    # Ghép list dài = count: UC id thật trước, rồi @handle, rồi filler để đủ số.
    result = list(ids)
    for h in handles:
        if len(result) >= count:
            break
        if h not in result:
            result.append(h)
    _k = 0
    while len(result) < count:
        result.append(f"_ch{_k}")
        _k += 1
    return result


async def do_accept_brand_invite(ws_url: str, email: str = "", password: str = "",
                                 totp_secret: str = "",
                                 log_fn=print) -> tuple[bool, str, str]:
    """CHẤP NHẬN QUẢN TRỊ: vào Brand Accounts → 'Lời mời đang chờ' → từng lời mời → 'CHẤP NHẬN'.
    CHẤP NHẬN TẤT CẢ lời mời đang chờ. Không có lời mời → vẫn coi là THÀNH CÔNG (ghi chú rõ).
    ⚙ Các mốc nhận diện ĐÃ KIỂM CHỨNG TRÊN TRANG THẬT (không phụ thuộc ngôn ngữ):
        • Trang danh sách lời mời : URL  …/brandaccounts?si=1
        • Mỗi lời mời             : thẻ <a> có href kết thúc bằng '/accept'
        • Nút chấp nhận           : div[jsname="no16zc"]  (dự phòng: chữ Accept/Chấp nhận/…)
        • Chấp nhận XONG          : URL đổi từ '…/accept' → '…/view'
    Trả (success, code, message)."""
    async with async_playwright() as p:
        log_fn("  [CNQT] Kết nối browser…")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        try:
            await ctx.add_cookies([
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".google.com", "path": "/"},
            ])
        except Exception:
            pass
        page = await ctx.new_page()

        async def _cant_verify() -> bool:
            try:
                _t = (await page.evaluate("() => document.body.innerText") or "").lower()
                return ("couldn't verify" in _t or "couldn`t verify" in _t
                        or "không thể xác minh" in _t or "cannot verify" in _t)
            except Exception:
                return False

        async def _reauth() -> bool:
            """Google hỏi lại mật khẩu → nhập pass, rồi 2FA nếu cần."""
            for _ in range(6):
                if "accounts.google.com" not in (page.url or ""):
                    return True
                if await _cant_verify():
                    return False
                try:
                    _has_pw = await page.locator('input[type="password"]').count() > 0
                except Exception:
                    _has_pw = False
                if _has_pw and password:
                    log_fn("  [CNQT] Nhập lại mật khẩu…")
                    await _reauth_if_needed(page, password, log_fn)
                    await page.wait_for_timeout(2500)
                    continue
                if totp_secret:
                    try:
                        if await _try_totp(page, totp_secret, log_fn):
                            await page.wait_for_timeout(2500)
                            continue
                    except Exception:
                        pass
                await page.wait_for_timeout(1500)
            return "accounts.google.com" not in (page.url or "")

        async def _invite_links() -> list:
            """Danh sách href các lời mời đang chờ (href kết thúc '/accept')."""
            try:
                return await page.evaluate(r"""() => {
                    const out = [];
                    for (const a of document.querySelectorAll('a[href]')) {
                        const h = a.getAttribute('href') || '';
                        const p = h.split('?')[0].split('#')[0];
                        if (/\/accept\/?$/.test(p) && out.indexOf(h) < 0) out.push(h);
                    }
                    return out;
                }""") or []
            except Exception:
                return []

        async def _click_accept() -> bool:
            """Bấm nút CHẤP NHẬN trên trang /accept (jsname ổn định + dự phòng theo chữ)."""
            try:
                return await page.evaluate(r"""() => {
                    const vis = e => e && e.offsetParent !== null;
                    // 1) định danh ổn định (đã kiểm chứng)
                    let e = document.querySelector('div[jsname="no16zc"]');
                    if (vis(e)) { try { e.click(); return true; } catch (x) {} }
                    // 2) dự phòng: theo chữ nhiều ngôn ngữ
                    const W = ['accept','chấp nhận','chap nhan','ยอมรับ','수락','接受','承諾',
                               'aceptar','accepter','akzeptieren','aceitar'];
                    for (const x of document.querySelectorAll('div[jsname], button, [role="button"]')) {
                        if (!vis(x)) continue;
                        const t = (x.innerText || '').trim().toLowerCase();
                        if (W.indexOf(t) < 0) continue;
                        const r = x.getBoundingClientRect();
                        if (r.width < 40 || r.height < 20) continue;
                        try { x.click(); return true; } catch (err) {}
                    }
                    return false;
                }""")
            except Exception:
                return False

        # ── B1: Mở THẲNG trang danh sách lời mời (…/brandaccounts?si=1) ──
        log_fn("  [CNQT] Mở trang Lời mời đang chờ…")
        try:
            await page.goto("https://myaccount.google.com/brandaccounts?si=1&hl=en",
                            wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3000)
        except Exception:
            pass
        if "accounts.google.com" in (page.url or ""):
            if not await _reauth():
                if await _cant_verify():
                    return False, "2FA7D", "2FA 7 ngày (Google chặn: We couldn't verify it's you)"
                return False, "", "Không qua được xác minh khi mở trang lời mời"
            await page.wait_for_timeout(2000)

        _links = await _invite_links()
        if not _links:
            # thử lại qua trang gốc + bấm mục 'Lời mời' (phòng khi ?si=1 không ăn)
            try:
                await page.goto("https://myaccount.google.com/brandaccounts?pli=1&hl=en",
                                wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2500)
            except Exception:
                pass
            try:
                # mục 'Lời mời' = link có path kết thúc bằng 'brandaccounts' (khác
                # notificationpreferences và /view) — chỉ BẤM ĐƯỢC khi CÓ lời mời.
                _ok = await page.evaluate(r"""() => {
                    for (const a of document.querySelectorAll('a[href]')) {
                        if (a.offsetParent === null) continue;
                        const p = (a.getAttribute('href') || '').split('?')[0].split('#')[0];
                        if (/(^|\/)brandaccounts\/?$/.test(p)) { a.click(); return true; }
                    }
                    return false;
                }""")
                if _ok:
                    await page.wait_for_timeout(3000)
            except Exception:
                pass
            _links = await _invite_links()

        if not _links:
            log_fn("  [CNQT] ⓘ Không có lời mời nào đang chờ.")
            return True, "", "Chấp nhận QT: KHÔNG có lời mời nào đang chờ (có thể đã nhận trước đó)"

        log_fn(f"  [CNQT] Có {len(_links)} lời mời đang chờ → chấp nhận tất cả…")
        _done, _fail = 0, []
        for _i in range(len(_links) + 2):        # +2 vòng dự phòng, luôn lấy lại danh sách
            _links = await _invite_links()
            if not _links:
                break
            _href = _links[0]
            _url = _href if _href.startswith("http") else \
                ("https://myaccount.google.com/" + _href.lstrip("/"))
            try:
                await page.goto(_url, wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2500)
            except Exception:
                pass
            if "accounts.google.com" in (page.url or ""):
                if not await _reauth():
                    if await _cant_verify():
                        return False, "2FA7D", "2FA 7 ngày (Google chặn xác minh)"
                    _fail.append("không qua xác minh")
                    break
                await page.wait_for_timeout(2000)
            # bấm CHẤP NHẬN — ⚠ KIỂM TRA KẾT QUẢ ĐỘC LẬP với việc click:
            # (lỗi cũ: chỉ kiểm URL khi click trả True → click ăn nhưng URL đổi chậm thì các
            #  vòng sau không còn nút, click trả False nên KHÔNG kiểm nữa → báo thất bại OAN.)
            async def _accepted() -> bool:
                """Đã chấp nhận xong: rời khỏi trang '/accept' (thường sang '/view')."""
                if "/accept" not in (page.url or ""):
                    return True
                try:   # dự phòng: trang chi tiết brand có nút 'Quản lý quyền/Manage permissions'
                    return await page.evaluate(r"""() => {
                        const t = (document.body.innerText || '').toLowerCase();
                        return t.indexOf('manage permissions') >= 0
                            || t.indexOf('quản lý quyền') >= 0
                            || t.indexOf('จัดการสิทธิ') >= 0
                            || t.indexOf('권한 관리') >= 0;
                    }""")
                except Exception:
                    return False

            _ok = False
            for _t in range(6):
                if await _accepted():        # kiểm TRƯỚC mỗi vòng (bất kể click có ăn hay không)
                    _ok = True
                    break
                if await _click_accept():
                    await page.wait_for_timeout(2500)
                    if await _accepted():
                        _ok = True
                        break
                await page.wait_for_timeout(1200)
            if _ok:
                _done += 1
                log_fn(f"  [CNQT] ✓ Đã chấp nhận lời mời #{_done}")
            else:
                _fail.append("không bấm được nút Chấp nhận")
                try:
                    await page.screenshot(path=_dbg_path("debug_cnqt.png"), timeout=5000)
                except Exception:
                    pass
                break
            # quay lại danh sách xem còn lời mời khác không
            try:
                await page.goto("https://myaccount.google.com/brandaccounts?si=1&hl=en",
                                wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2500)
            except Exception:
                pass

        # ── XÁC MINH CUỐI (theo yêu cầu): đợi 3s → load lại trang Brand Accounts →
        #    nếu KHÔNG CÒN lời mời nào ⇒ BÁO THÀNH CÔNG.
        #    Mốc nhận diện: mục 'Lời mời đang chờ' CHỈ là thẻ <a> (bấm được) KHI CÒN lời mời;
        #    hết lời mời thì nó chỉ còn <li> (không bấm được).
        log_fn("  [CNQT] ⏳ Đợi 3s rồi mở lại trang Brand Accounts để kiểm tra…")
        await page.wait_for_timeout(3000)
        _still = None          # None = không kiểm được | True = còn | False = hết
        try:
            await page.goto("https://myaccount.google.com/brandaccounts?pli=1&hl=en",
                            wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2500)
            if "accounts.google.com" in (page.url or ""):
                await _reauth()
                await page.wait_for_timeout(2000)
            _still = await page.evaluate(r"""() => {
                for (const a of document.querySelectorAll('a[href]')) {
                    if (a.offsetParent === null) continue;
                    const p = (a.getAttribute('href') || '').split('?')[0].split('#')[0];
                    // mục 'Lời mời đang chờ' = link có path kết thúc bằng 'brandaccounts'
                    if (/(^|\/)brandaccounts\/?$/.test(p)) return true;   // CÒN lời mời
                }
                return false;                                            // HẾT lời mời
            }""")
        except Exception:
            _still = None

        if _still is False:
            _n = f" ({_done} lời mời)" if _done else ""
            log_fn(f"  [CNQT] ✅ Kiểm tra lại: KHÔNG còn lời mời nào → hoàn tất{_n}.")
            return True, "", f"Chấp nhận QT OK{_n} — đã kiểm tra lại: hết lời mời"
        if _still is True:
            log_fn(f"  [CNQT] ⚠ Kiểm tra lại: VẪN CÒN lời mời chưa chấp nhận (đã xong {_done}).")
            if _done:
                return True, "", (f"Chấp nhận QT: xong {_done} nhưng VẪN CÒN lời mời chưa nhận")
            return False, "", ("Chấp nhận QT thất bại: vẫn còn lời mời chưa nhận"
                               f"{' — ' + '; '.join(_fail[:2]) if _fail else ''} (xem debug_cnqt.png)")

        # không kiểm tra lại được → dựa vào kết quả vòng chấp nhận
        if _done and not _fail:
            log_fn(f"  [CNQT] ✅ Đã chấp nhận {_done} lời mời quản trị.")
            return True, "", f"Chấp nhận QT OK ({_done} lời mời)"
        if _done and _fail:
            return True, "", f"Chấp nhận QT: xong {_done}, lỗi: {'; '.join(_fail[:2])}"
        return False, "", f"Chấp nhận QT thất bại: {'; '.join(_fail[:2]) or 'không rõ'} (xem debug_cnqt.png)"


async def do_add_brand_admin(ws_url: str, email: str = "", password: str = "",
                             owner_email: str = "", totp_secret: str = "",
                             skip_create_move: bool = False,
                             log_fn=print) -> tuple[bool, str, str]:
    """ADD QUẢN TRỊ cho KÊNH THƯƠNG HIỆU. Luồng:
      1) Vào YouTube, đếm số kênh: 1 = chỉ kênh chính; ≥2 = đã có kênh thương hiệu.
      2) Nếu 1 kênh → TẠO thêm 1 kênh thương hiệu; nếu đã ≥2 → bỏ qua bước tạo.
      3) Chuyển sang kênh thương hiệu.
      4) Add 'owner_email' làm CHỦ SỞ HỮU (owner) kênh thương hiệu.
    (Bước 2 & 4 sẽ hoàn thiện theo hướng dẫn từng bước.) Trả (success, '', message)."""
    async with async_playwright() as p:
        log_fn("  [ADDQT] Kết nối browser…")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        try:
            await ctx.add_cookies([
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".youtube.com", "path": "/"},
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".google.com", "path": "/"},
            ])
        except Exception:
            pass
        page = await ctx.new_page()
        import re as __re_v

        async def _cant_verify() -> bool:
            """True nếu Google chặn xác minh ('We couldn't verify it's you' / 'Không thể xác
            minh danh tính') — thường là kỳ chờ 7 ngày, không tự động qua được."""
            for _t in [r"couldn'?t verify it'?s you", r"can'?t verify it'?s you",
                       r"Không thể xác minh danh tính", r"không thể xác minh"]:
                try:
                    if await page.get_by_text(__re_v.compile(_t, __re_v.I)).count() > 0:
                        return True
                except Exception:
                    pass
            return False

        # Helper dùng chung cho B3 và B4: qua màn xác minh lại (mật khẩu → 2FA).
        async def _reauth_pw_2fa(rounds: int = 6) -> bool:
            """Trả True nếu đã qua (không còn ở trang accounts.google.com)."""
            for _ in range(rounds):
                await page.wait_for_timeout(2000)
                if await _cant_verify():
                    return False   # bị chặn 'We couldn't verify it's you' → dừng
                if "accounts.google.com" not in (page.url or ""):
                    return True
                try:
                    _has_pw = await page.locator('input[type="password"]:visible').count() > 0
                except Exception:
                    _has_pw = False
                if _has_pw and password:
                    log_fn("  [ADDQT] Nhập lại mật khẩu…")
                    await _reauth_if_needed(page, password, log_fn)
                    await page.wait_for_timeout(2500)
                    continue
                if totp_secret:
                    try:
                        if await _try_totp(page, totp_secret, log_fn):
                            await page.wait_for_timeout(2500)
                            continue
                    except Exception:
                        pass
                await page.wait_for_timeout(1500)
            return "accounts.google.com" not in (page.url or "")

        # ── B1: ĐẾM SỐ KÊNH ────────────────────────────────────────────────
        # 'Add Thêm QT' (skip_create_move=True): CHỈ add owner → bỏ qua đếm/tạo/chuyển kênh.
        if skip_create_move:
            _has_brand = True
            log_fn("  [ADDQT] (Add Thêm QT) → chỉ add mail quản trị, BỎ QUA tạo/chuyển kênh.")
        else:
            log_fn("  [ADDQT] Kiểm tra số kênh của tài khoản…")
            ids = await _list_channel_ids(page, log_fn)
            if not ids:
                return False, "", "Không đọc được danh sách kênh (mạng chậm/chưa đăng nhập?)"
            n = len(ids)
            log_fn(f"  [ADDQT] Tài khoản có {n} kênh: {', '.join(ids[:4])}")
            if n >= 2:
                log_fn("  [ADDQT] → ĐÃ CÓ kênh thương hiệu (≥2 kênh) → bỏ qua bước tạo.")
                _has_brand = True
            else:
                log_fn("  [ADDQT] → Chỉ có 1 kênh (kênh chính) → CẦN TẠO kênh thương hiệu.")
                _has_brand = False

        # ── B2: TẠO kênh thương hiệu (nếu chưa có) ─────────────────────────
        if not _has_brand:
            log_fn("  [ADDQT] Tạo kênh thương hiệu…")

            # (2.2) LẤY TÊN kênh chính CHẮC CHẮN: đọc og:title / tiêu đề trang kênh chính
            #       (id = ids[0]). Cách cũ mò link 'a[href*=/channel/]' bắt nhầm 'Visit source'.
            _main_cid = ids[0] if ids else ""
            _cname = ""
            if _main_cid:
                try:
                    await page.goto(f"https://www.youtube.com/channel/{_main_cid}?hl=en",
                                    wait_until="domcontentloaded", timeout=40000)
                    await page.wait_for_timeout(2500)
                    _cname = await page.evaluate(r"""() => {
                        var og = document.querySelector('meta[property="og:title"]');
                        if (og && og.content) return og.content.trim();
                        try {
                            var t = window.ytInitialData
                              && ytInitialData.metadata
                              && ytInitialData.metadata.channelMetadataRenderer
                              && ytInitialData.metadata.channelMetadataRenderer.title;
                            if (t) return String(t).trim();
                        } catch(e){}
                        var m = (document.title||'').replace(/ - YouTube$/,'').trim();
                        return m || '';
                    }""")
                except Exception:
                    _cname = ""
            _cname = (_cname or "").strip()
            if not _cname or _cname.lower() in ("youtube", "visit source"):
                return False, "", f"Không lấy được tên kênh chính (đọc được: '{_cname}')"
            log_fn(f"  [ADDQT] Tên kênh chính (dùng cho kênh TH): {_cname}")

            # (2.1) Mở trang DANH SÁCH KÊNH (channel_switcher) — nơi CÓ nút tạo kênh.
            try:
                await page.goto("https://www.youtube.com/channel_switcher?hl=en",
                                wait_until="domcontentloaded", timeout=40000)
                await page.wait_for_timeout(3000)
            except Exception:
                try:
                    await page.goto("https://www.youtube.com/account?hl=en",
                                    wait_until="domcontentloaded", timeout=40000)
                    await page.wait_for_timeout(2500)
                except Exception:
                    return False, "", "Không mở được trang danh sách kênh"

            # (2.3) Bấm nút TẠO KÊNH.
            # ⚠⚠ LỖI CŨ: chỉ tìm chữ 'Create a new channel' — nhưng nút thật là
            #    'Create a channel' (thiếu chữ 'new' ⇒ KHÔNG khớp) ⇒ không bấm được, rồi
            #    goto '/create_channel' KHÔNG có token ⇒ bị đá về trang kênh, hộp không mở.
            #    ⇒ NHẮM THEO HREF '/create_channel' (đã kiểm chứng: nút là
            #      <a href="/create_channel?channel_creation_token=…">), không phụ thuộc ngôn ngữ.
            _clicked = False
            try:
                b = page.locator('a[href*="create_channel"]')
                n = await b.count()
                for i in range(min(n, 3)):
                    el = b.nth(i)
                    if await el.is_visible():
                        await el.click(timeout=5000)
                        _clicked = True
                        log_fn("  [ADDQT] ✓ Bấm nút tạo kênh (theo href create_channel)")
                        break
            except Exception:
                pass
            if not _clicked:      # dự phòng: theo CHỮ, nhiều biến thể + ngôn ngữ
                for _t in ["Create a channel", "Create channel", "Create a new channel",
                           "Tạo kênh mới", "Tạo kênh", "สร้างช่อง", "채널 만들기", "创建频道"]:
                    try:
                        b = page.locator(f'a:has-text("{_t}"), button:has-text("{_t}"), '
                                         f'[role="button"]:has-text("{_t}"), '
                                         f'tp-yt-paper-item:has-text("{_t}")')
                        if await b.count() > 0 and await b.first.is_visible():
                            await b.first.click(timeout=5000)
                            _clicked = True
                            log_fn(f"  [ADDQT] ✓ Bấm '{_t}'")
                            break
                    except Exception:
                        pass
            if not _clicked:
                try:
                    await page.screenshot(path=_dbg_path("debug_addqt_create.png"), timeout=5000)
                except Exception:
                    pass
                return False, "", ("Không bấm được nút tạo kênh trên trang danh sách kênh "
                                   "(xem debug_addqt_create.png)")
            await page.wait_for_timeout(3500)   # chờ hộp 'How you'll appear' mở

            # (2.4) Hộp 'How you'll appear': điền Name = tên kênh chính. Tìm ô Name TRÊN MỌI FRAME.
            async def _fill_name() -> bool:
                """Điền TÊN kênh vào ô 'Name' BÊN TRONG HỘP THOẠI.
                ⚠⚠ LỖI CŨ (đã kiểm chứng trên trang thật): ô 'Name' KHÔNG phải input[type=text];
                   selector cũ 'input[type=text]' lại khớp Ô TÌM KIẾM YouTube
                   (name="search_query") ⇒ tool GÕ TÊN VÀO Ô TÌM KIẾM, ô Name vẫn trống nên
                   nút 'Tạo kênh' không hoạt động.
                   ⇒ CHỈ điền vào input NẰM TRONG hộp thoại, LOẠI ô tìm kiếm, và XÁC MINH
                     giá trị sau khi gõ. KHÔNG bao giờ gõ ra ngoài hộp."""
                _DLG = ('[role="dialog"]', '[aria-modal="true"]',
                        'tp-yt-paper-dialog', 'ytcp-dialog')
                for fr in ([page] + list(page.frames)):
                    for _dsel in _DLG:
                        try:
                            dlg = fr.locator(_dsel)
                            if await dlg.count() == 0:
                                continue
                            d = dlg.last
                            # mọi ô nhập trong hộp, BỎ ô tìm kiếm + ô ẩn
                            inp = d.locator('input:not([name="search_query"]):not([type="hidden"])'
                                            ':not([type="checkbox"]):not([type="radio"]), textarea')
                            nq = await inp.count()
                            for i in range(min(nq, 4)):
                                el = inp.nth(i)
                                try:
                                    if not await el.is_visible():
                                        continue
                                    await el.click(timeout=3000)
                                    try:
                                        await el.fill("")
                                    except Exception:
                                        pass
                                    await el.type(_cname, delay=30)
                                    await page.wait_for_timeout(400)
                                    # XÁC MINH đã vào đúng ô (ô Name phải có giá trị)
                                    try:
                                        _v = ((await el.input_value()) or "").strip()
                                    except Exception:
                                        _v = ""
                                    if _v:
                                        return True
                                except Exception:
                                    continue
                        except Exception:
                            pass
                return False

            _name_filled = False
            for _ in range(15):
                if await _fill_name():
                    _name_filled = True
                    break
                await page.wait_for_timeout(1000)
            if not _name_filled:
                try:
                    await page.screenshot(path=_dbg_path("debug_addqt_create.png"), timeout=5000)
                except Exception:
                    pass
                return False, "", "Không thấy ô Name để tạo kênh (xem debug_addqt_create.png)"
            log_fn(f"  [ADDQT] ✓ Điền Name = {_cname}, chờ Handle tự đề xuất…")
            await page.wait_for_timeout(4000)   # chờ YouTube đề xuất handle (dấu tích xanh)

            # (2.5) Bấm 'Create channel' — NHIỀU NGÔN NGỮ + theo CẤU TRÚC (nút chính bên phải),
            #        có CHỜ nút bật (handle hợp lệ mới bật) và bỏ qua nút Cancel.
            _CRE_W = ["create channel", "create", "tạo kênh", "tạo", "สร้างช่อง", "สร้าง",
                      "채널 만들기", "만들기", "创建频道", "创建", "建立頻道", "建立",
                      "チャンネルを作成", "作成", "crear canal", "crear", "criar canal", "criar",
                      "créer une chaîne", "créer", "kanal erstellen", "erstellen"]
            _CAN_W = ["cancel", "hủy", "huỷ", "ยกเลิก", "취소", "取消", "キャンセル",
                      "cancelar", "annuler", "abbrechen"]

            async def _click_create_btn() -> bool:
                try:
                    return await page.evaluate(r"""(args) => {
                        const [CRE, CAN] = args;
                        const vis = e => {
                            if (!e || e.offsetParent === null) return false;
                            const r = e.getBoundingClientRect();
                            return r.width > 40 && r.height > 18;
                        };
                        const dis = e => {
                            let n = e;
                            for (let k = 0; k < 4 && n; k++) {
                                if (n.getAttribute && (n.getAttribute('aria-disabled') === 'true'
                                        || n.hasAttribute('disabled'))) return true;
                                n = n.parentElement;
                            }
                            return false;
                        };
                        const cands = document.querySelectorAll(
                            'button, [role="button"], ytcp-button, tp-yt-paper-button, div[jsname]');
                        // 1) khớp CHỮ (nhiều ngôn ngữ), bỏ nút Cancel, bỏ nút đang tắt
                        for (const e of cands) {
                            if (!vis(e) || dis(e)) continue;
                            const t = (e.innerText || '').trim().toLowerCase();
                            if (!t || t.length > 30) continue;
                            if (CAN.some(c => t === c)) continue;
                            if (CRE.some(c => t === c)) { try { e.click(); return true; } catch (x) {} }
                        }
                        // 2) theo CẤU TRÚC: trong hộp thoại, nút BẬT nằm XA NHẤT bên phải
                        //    (Cancel luôn ở trái) — không phụ thuộc ngôn ngữ.
                        let dlg = null, ba = 1e18;
                        for (const d of document.querySelectorAll('[role="dialog"], tp-yt-paper-dialog, ytcp-dialog')) {
                            if (d.offsetParent === null) continue;
                            const r = d.getBoundingClientRect();
                            const a = r.width * r.height;
                            if (a > 0 && a < ba) { ba = a; dlg = d; }
                        }
                        const root = dlg || document;
                        let best = null, bx = -1;
                        for (const e of root.querySelectorAll('button, [role="button"], ytcp-button, tp-yt-paper-button')) {
                            if (!vis(e) || dis(e)) continue;
                            const t = (e.innerText || '').trim().toLowerCase();
                            if (CAN.some(c => t === c)) continue;      // bỏ Cancel
                            const r = e.getBoundingClientRect();
                            if (r.left > bx) { bx = r.left; best = e; }
                        }
                        if (best) { try { best.click(); return true; } catch (x) {} }
                        return false;
                    }""", [_CRE_W, _CAN_W])
                except Exception:
                    return False

            async def _click_create_old() -> bool:
                """Bấm nút tạo kênh BÊN TRONG HỘP THOẠI.
                ⚠⚠ LỖI CŨ (đã kiểm chứng trên trang thật): trang có 2 nút CÙNG CHỮ —
                   <a> NGOÀI hộp (nút MỞ hộp, y≈150) và <button> TRONG hộp (y≈922).
                   Dùng .first sẽ bấm trúng nút NGOÀI → hộp đóng/mở lại → KHÔNG tạo được kênh.
                   ⇒ Phải khoanh vùng trong dialog và ưu tiên thẻ <button>."""
                for _dsel in ('[role="dialog"]', '[aria-modal="true"]',
                              'tp-yt-paper-dialog', 'ytcp-dialog'):
                    try:
                        dlg = page.locator(_dsel)
                        if await dlg.count() == 0:
                            continue
                        d = dlg.last
                        for _w in ["Create channel", "Tạo kênh", "Create", "Tạo"]:
                            b = d.locator(f'button:has-text("{_w}")')
                            n = await b.count()
                            for i in range(n):
                                el = b.nth(i)
                                if not await el.is_visible():
                                    continue
                                _t = ((await el.inner_text()) or "").strip().lower()
                                if _t in ("cancel", "hủy", "huỷ"):
                                    continue
                                await el.click(timeout=5000)
                                return True
                    except Exception:
                        pass
                return False

            async def _find_create_enabled() -> dict:
                """Tìm nút TẠO KÊNH trong hộp — CHỈ trả toạ độ khi nút ĐÃ BẬT.
                ⚠ TUYỆT ĐỐI không bấm 'Cancel'/'Choose photo' (từng bấm nhầm → đóng hộp,
                  không tạo được kênh). Chỉ khớp CHỮ tạo-kênh, và phải KHÔNG disabled."""
                try:
                    return await page.evaluate(r"""(args) => {
                        const [CRE, CAN] = args;
                        const vis = e => {
                            if (!e || e.offsetParent === null) return false;
                            const r = e.getBoundingClientRect();
                            return r.width > 40 && r.height > 18;
                        };
                        const dis = e => {
                            let n = e;
                            for (let k = 0; k < 4 && n; k++) {
                                if (n.getAttribute && (n.getAttribute('aria-disabled') === 'true'
                                        || n.hasAttribute('disabled'))) return true;
                                n = n.parentElement;
                            }
                            return false;
                        };
                        const DLG = '[role="dialog"], [aria-modal="true"], tp-yt-paper-dialog, ytcp-dialog';
                        let seen = [];
                        for (const e of document.querySelectorAll(
                                'button, [role="button"], ytcp-button, tp-yt-paper-button')) {
                            if (!vis(e)) continue;
                            // ⚠ CHỈ nhận nút BÊN TRONG hộp thoại (nút cùng chữ ở ngoài là nút MỞ hộp)
                            if (!e.closest(DLG)) continue;
                            const t = (e.innerText || '').trim().toLowerCase();
                            if (!t || t.length > 30) continue;
                            seen.push(t + (dis(e) ? '(tat)' : '(bat)'));
                            if (CAN.some(c => t === c)) continue;         // KHÔNG bấm Cancel
                            if (!CRE.some(c => t === c)) continue;        // phải đúng chữ tạo kênh
                            if (dis(e)) return {wait: true, seen: seen};  // có nút nhưng CHƯA BẬT
                            const r = e.getBoundingClientRect();
                            return {x: r.left + r.width / 2, y: r.top + r.height / 2, seen: seen};
                        }
                        return {seen: seen};
                    }""", [_CRE_W, _CAN_W]) or {}
                except Exception:
                    return {}

            _created = False
            _seen_last = []
            for _try_c in range(15):         # chờ tới ~30s cho handle đề xuất + nút BẬT
                # 1) CÁCH CŨ (Playwright click thật) — chỉ ăn khi nút đã bật
                if await _click_create_old():
                    _created = True
                    log_fn("  [ADDQT] ✓ Bấm 'Create channel'")
                    break
                # 2) DỰ PHÒNG AN TOÀN: chỉ bấm khi tìm ĐÚNG nút tạo-kênh và nút ĐÃ BẬT
                _g = await _find_create_enabled()
                _seen_last = _g.get("seen") or _seen_last
                if _g.get("x") is not None:
                    await page.mouse.click(_g["x"], _g["y"])      # click CHUỘT THẬT
                    _created = True
                    log_fn("  [ADDQT] ✓ Bấm 'Create channel' (dự phòng: toạ độ, nút đã bật)")
                    break
                if _g.get("wait"):
                    log_fn(f"  [ADDQT] (chờ nút tạo kênh BẬT… {_try_c + 1}/15)")
                await page.wait_for_timeout(2000)
            if not _created:
                try:
                    await page.screenshot(path=_dbg_path("debug_addqt_create.png"), timeout=5000)
                except Exception:
                    pass
                try:   # DUMP các nút đang có để chẩn đoán chính xác
                    _btns = await page.evaluate(r"""() => {
                        const out = [];
                        for (const e of document.querySelectorAll(
                                'button, [role="button"], ytcp-button, tp-yt-paper-button')) {
                            if (e.offsetParent === null) continue;
                            const r = e.getBoundingClientRect();
                            if (r.width < 20 || r.height < 12) continue;
                            let d = false, n = e;
                            for (let k = 0; k < 4 && n; k++) {
                                if (n.getAttribute && (n.getAttribute('aria-disabled') === 'true'
                                        || n.hasAttribute('disabled'))) { d = true; break; }
                                n = n.parentElement;
                            }
                            out.push('<' + e.tagName + '> disabled=' + d
                                + ' x=' + Math.round(r.left) + ' y=' + Math.round(r.top)
                                + ' :: ' + JSON.stringify((e.innerText || '').trim().slice(0, 40)));
                        }
                        return 'URL-path: ' + location.pathname + '\n' + out.slice(0, 25).join('\n');
                    }""")
                    with open(_dbg_path("debug_addqt_create.txt"), "w", encoding="utf-8") as _f:
                        _f.write("### CAC NUT THAY DUOC (bat/tat) ###\n"
                                 + ", ".join(_seen_last or []) + "\n\n"
                                 + (_btns or "(không thấy nút nào)"))
                except Exception:
                    pass
                return False, "", ("Không bấm được nút 'Create channel' "
                                   "(xem debug_addqt_create.png + debug_addqt_create.txt)")
            await page.wait_for_timeout(6000)   # chờ YouTube tạo xong + chuyển trang

            # (2.6) XÁC MINH: kênh mới cần THỜI GIAN lan vào channel_switcher → DÒ LẠI NHIỀU LẦN
            #       (tối đa ~40s). Thành công nếu có ≥2 kênh HOẶC xuất hiện channel ID MỚI
            #       (khác kênh chính _main_cid). Trước đây đọc 1 lần nên tưởng thất bại.
            _created_ok = False
            ids2 = ids
            for _try in range(7):
                await page.wait_for_timeout(5000)
                ids2 = await _list_channel_ids(page, log_fn)
                _new_ids = [i for i in ids2 if i and i != _main_cid]
                if len(ids2) >= 2 or _new_ids:
                    _created_ok = True
                    break
                log_fn(f"  [ADDQT] Chờ kênh thương hiệu hiện trong danh sách… "
                       f"(lần {_try + 1}/7, đang thấy {len(ids2)} kênh)")
            if not _created_ok:
                try:
                    await page.screenshot(path=_dbg_path("debug_addqt_create.png"), timeout=5000)
                except Exception:
                    pass
                return False, "", (f"Tạo kênh thương hiệu THẤT BẠI (sau ~40s vẫn {len(ids2)} kênh). "
                                   f"Xem debug_addqt_create.png")
            log_fn(f"  [ADDQT] ✅ Đã tạo kênh thương hiệu (giờ thấy {len(ids2)} kênh).")
            ids = ids2   # cập nhật danh sách cho các bước sau

        # ── B3: CHUYỂN (MOVE) kênh chính sang tài khoản thương hiệu ─────────
        # Chỉ làm B3 khi VỪA TẠO kênh TH ở B2 (kênh chính chưa nằm trong brand account).
        # Nếu account ĐÃ có sẵn ≥2 kênh từ đầu → coi như đã chuyển rồi, bỏ qua B3.
        # ── B3: CHUYỂN kênh chính vào brand account ─────────────────────────
        # LUÔN thử move (kể cả khi đã ≥2 kênh) — vì "2 kênh" KHÔNG chắc đã move kênh chính.
        # Nếu KHÔNG thấy nút 'Move channel to a brand account' (đã move rồi / đã ở brand) → BỎ QUA êm.
        async def _do_move_channel() -> tuple[str, str]:
            # trả: ("ok","") đã move | ("skip","") không cần move | ("2fa7d","") | ("err", msg)
            try:
                await page.goto("https://www.youtube.com/account_advanced?hl=en",
                                wait_until="domcontentloaded", timeout=40000)
                await page.wait_for_timeout(3000)
            except Exception:
                return "err", "Không mở được trang Advanced settings (account_advanced)"

            # (3.2) Tìm & bấm 'Move channel to a brand account' — DÒ tới ~12s. Không có → coi như đã move.
            _mv_clicked = False
            for _ in range(6):
                if await _click_by_text(
                        page, ["Move channel to a brand account", "Move channel", "Di chuyển kênh"],
                        log_fn, tag="[ADDQT] ", click_timeout=5000):
                    _mv_clicked = True
                    break
                await page.wait_for_timeout(2000)
            if not _mv_clicked:
                return "skip", ""
            await page.wait_for_timeout(3000)

            # (3.3) Xác minh lại: mật khẩu → 2FA
            if not await _reauth_pw_2fa():
                if await _cant_verify():
                    return "2fa7d", ""
                return "err", "Không qua được xác minh (mật khẩu/2FA) khi move kênh"
            await page.wait_for_timeout(3000)

            # (3.4) Trang Transfer: tại brand account (đã có kênh trống) bấm 'Replace'
            _rep = False
            for _ in range(10):
                if await _click_by_text(page, ["Replace", "Thay thế"], log_fn,
                                        tag="[ADDQT] ", click_timeout=5000):
                    _rep = True
                    break
                await page.wait_for_timeout(1500)
            if not _rep:
                try:
                    await page.screenshot(path=_dbg_path("debug_addqt_move.png"), timeout=5000)
                except Exception:
                    pass
                return "err", "Không thấy nút 'Replace' ở trang Transfer (xem debug_addqt_move.png)"
            await page.wait_for_timeout(2500)

            # (3.5) Hộp 'Delete this channel?' → tích 'I understand and wish to proceed'
            _checked = False
            for _ in range(8):
                try:
                    cb = page.locator(
                        'tp-yt-paper-checkbox, [role="checkbox"], input[type="checkbox"]')
                    n = await cb.count()
                    for i in range(min(n, 4)):
                        e = cb.nth(i)
                        if await e.is_visible():
                            await e.click(timeout=3000)
                            _checked = True
                            break
                except Exception:
                    pass
                if _checked:
                    break
                await page.wait_for_timeout(1000)
            if not _checked:
                return "err", "Không tích được ô 'I understand and wish to proceed'"
            await page.wait_for_timeout(1000)

            # (3.6) Bấm 'Delete channel'
            if not await _click_by_text(page, ["Delete channel", "Xóa kênh", "Xoá kênh"],
                                        log_fn, tag="[ADDQT] ", click_timeout=5000):
                return "err", "Không bấm được 'Delete channel'"
            await page.wait_for_timeout(3000)

            # (3.7) Hộp 'Are you sure you want to move…' → bấm 'Move channel'
            _moved = False
            for _ in range(8):
                if await _click_by_text(page, ["Move channel", "Di chuyển kênh"], log_fn,
                                        tag="[ADDQT] ", click_timeout=5000):
                    _moved = True
                    break
                await page.wait_for_timeout(1500)
            if not _moved:
                return "err", "Không bấm được 'Move channel' (hộp xác nhận cuối)"
            await page.wait_for_timeout(8000)   # chờ YouTube xử lý move
            return "ok", ""

        # 'Add Thêm QT': BỎ QUA hẳn bước chuyển kênh, đi thẳng add owner.
        if not skip_create_move:
            log_fn("  [ADDQT] Kiểm tra/chuyển kênh chính sang tài khoản thương hiệu…")
            _mv, _mvmsg = await _do_move_channel()
            if _mv == "2fa7d":
                return False, "2FA7D", "2FA 7 ngày (Google chặn: We couldn't verify it's you)"
            if _mv == "err":
                return False, "", _mvmsg
            if _mv == "skip":
                log_fn("  [ADDQT] (ⓘ không thấy nút Move → kênh chính có vẻ đã ở brand account → bỏ qua move)")
            else:
                log_fn("  [ADDQT] ✅ Đã chuyển kênh chính sang tài khoản thương hiệu.")

        # ── B4: ADD owner_email làm CHỦ SỞ HỮU kênh thương hiệu ─────────────
        if not owner_email or "@" not in owner_email:
            # 'Add Thêm QT' CHỈ có mỗi việc add mail → không có mail = LỖI (không được báo OK).
            if skip_create_move:
                log_fn("  [ADDQT] ✗ KHÔNG có mail quản trị (cột E trống) → không add được.")
                return False, "", ("Add Thêm QT: THIẾU mail quản trị ở cột E "
                                   "(dòng account phải là: mail|pass|recovery|2fa|MAIL_QUẢN_TRỊ)")
            _msg = ("Đã có sẵn kênh TH (bỏ qua tạo/move)" if _has_brand
                    else "Đã tạo + chuyển kênh sang TH") + " — KHÔNG có mail quản trị (cột E trống)"
            log_fn("  [ADDQT] ⚠ Cột E (mail quản trị) trống → bỏ qua add owner.")
            return True, "", _msg

        log_fn(f"  [ADDQT] Add owner '{owner_email}' vào kênh thương hiệu…")
        import re as __re

        async def _brand_ids_html() -> set:
            try:
                html = await page.content()
            except Exception:
                return set()
            ids = set(__re.findall(r'brandaccounts/(\d{10,})', html))
            for m in __re.findall(r'data-id="(\d{15,})"', html):
                ids.add(m)
            return ids

        # (4.1) Đợi 10s rồi mở trang brandaccounts (ép tiếng Anh cho ổn định)
        await page.wait_for_timeout(10000)
        _target_id = ""
        for _ in range(15):
            try:
                await page.goto("https://myaccount.google.com/brandaccounts?pli=1&hl=en",
                                wait_until="domcontentloaded", timeout=40000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)
            _bids = await _brand_ids_html()
            if _bids:
                _target_id = sorted(_bids)[0]
                break
            await page.wait_for_timeout(1000)
        if not _target_id:
            try:
                await page.screenshot(path=_dbg_path("debug_addqt_owner.png"), timeout=5000)
            except Exception:
                pass
            return False, "", "Không thấy Brand Account để add owner (xem debug_addqt_owner.png)"

        # (4.2→4.3) Vào chi tiết brand + bấm 'Manage Permissions'; xử lý xác minh; bấm lại
        _detail = f"https://myaccount.google.com/brandaccounts/{_target_id}/view?hl=en"

        async def _click_manage() -> bool:
            for t in ["Manage permissions", "Manage Permissions", "Quản lý quyền",
                      "จัดการสิทธิ์", "관리 권한", "管理權限", "管理权限"]:
                try:
                    b = page.locator(f'button:has-text("{t}"), a:has-text("{t}"), '
                                     f'[role="button"]:has-text("{t}")')
                    n2 = await b.count()
                    for i in range(min(n2, 4)):
                        e = b.nth(i)
                        if await e.is_visible():
                            await e.click(timeout=5000)
                            return True
                except Exception:
                    pass
            return False

        async def _dialog_open() -> bool:
            # hộp Manage permissions có dòng 'Primary owner / Chủ sở hữu chính'
            for t in ["Primary owner", "Chủ sở hữu chính", "所有者", "주 소유자"]:
                try:
                    if await page.get_by_text(__re.compile(t, __re.I)).count() > 0:
                        return True
                except Exception:
                    pass
            return False

        _perms_url = f"https://myaccount.google.com/brandaccounts/{_target_id}/permissions?hl=en"
        _opened = False
        for _att in range(4):
            if f"/brandaccounts/{_target_id}" not in (page.url or ""):
                try:
                    await page.goto(_detail, wait_until="domcontentloaded", timeout=40000)
                    await page.wait_for_timeout(2500)
                except Exception:
                    continue
            if await _dialog_open():
                _opened = True
                break
            # thử nút 'Manage Permissions'; nếu KHÔNG có nút (trang biến thể) → mở THẲNG URL permissions
            if not await _click_manage():
                try:
                    await page.goto(_perms_url, wait_until="domcontentloaded", timeout=40000)
                    await page.wait_for_timeout(2500)
                except Exception:
                    pass
                if await _dialog_open():
                    _opened = True
                    break
            # dò 15s: hộp mở? / bị hỏi xác minh?
            for _ in range(15):
                await page.wait_for_timeout(1000)
                if await _dialog_open():
                    _opened = True
                    break
                if await _cant_verify():
                    return False, "2FA7D", "2FA 7 ngày (Google chặn: We couldn't verify it's you)"
                if "accounts.google.com" in (page.url or ""):
                    await _reauth_pw_2fa()
                    await page.wait_for_timeout(2000)
                    break   # về vòng ngoài, vào lại detail & bấm Manage lần nữa
            if _opened:
                break
        if not _opened:
            if await _cant_verify():
                return False, "2FA7D", "2FA 7 ngày (Google chặn: We couldn't verify it's you)"
            try:
                await page.screenshot(path=_dbg_path("debug_addqt_owner.png"), timeout=5000)
            except Exception:
                pass
            # DUMP nút/link thật trên trang brand để phân tích (không đoán)
            try:
                _btns = await page.evaluate(r"""() => {
                    const out = [];
                    for (const e of document.querySelectorAll('button, a, [role="button"], [role="link"]')) {
                        if (e.offsetParent === null) continue;
                        const t = (e.textContent||'').trim().slice(0,60);
                        const href = e.getAttribute('href') || '';
                        if (t || href) out.push('<'+e.tagName+'> '+JSON.stringify(t)
                            +(href?(' href='+href.slice(0,80)):''));
                    }
                    return 'URL: '+location.href+'\n\n'+out.join('\n');
                }""")
                with open(_dbg_path("debug_addqt_dom.txt"), "w", encoding="utf-8") as _f:
                    _f.write(_btns or "(rỗng)")
            except Exception:
                pass
            return False, "", ("Không mở được hộp Quản lý quyền — trang brand không có nút Manage "
                               "(xem debug_addqt_owner.png + debug_addqt_dom.txt)")

        # (4.5b) KIỂM TRA QUYỀN CỦA CHÍNH MÌNH trong hộp 'Manage permissions'.
        # Google CHỈ cho Owner / Primary owner thêm người dùng làm Owner. Nếu tài khoản đang
        # đăng nhập chỉ là 'Manager' → KHÔNG BAO GIỜ chọn được vai trò Owner (INVITE luôn xám).
        # → Phát hiện sớm để báo lỗi rõ ràng, không phí 6 vòng thử vô ích.
        try:
            _my = await page.evaluate(r"""() => {
                // Tìm hàng 'You (...)' rồi đọc CHÍNH XÁC ô vai trò HIỂN THỊ trên hàng đó.
                // ⚠ KHÔNG đọc innerText cả vùng: ô vai trò là dropdown có option ẩn ('Manager')
                //   → đọc cả vùng sẽ nhận nhầm là 'manager' dù thực tế đang là 'Owner'.
                const EX = {'owner':'owner', 'chủ sở hữu':'owner',
                            'manager':'manager', 'người quản lý':'manager',
                            'primary owner':'primary', 'chủ sở hữu chính':'primary'};
                let you = null;
                for (const e of document.querySelectorAll('*')) {
                    if (e.offsetParent === null) continue;
                    const t = (e.innerText || '').trim();
                    if (!/^You\s*\(|^Bạn\s*\(/i.test(t)) continue;
                    if (t.length > 80) continue;
                    you = e; break;
                }
                if (!you) return '';
                const yr = you.getBoundingClientRect();
                const ycy = yr.top + yr.height / 2;
                // quét phần tử NHỎ (lá) có text ĐÚNG BẰNG tên vai trò, nằm CÙNG HÀNG với 'You (...)'
                let best = '', bestArea = 1e18;
                for (const e of document.querySelectorAll('*')) {
                    if (e.offsetParent === null) continue;
                    if (e.children.length > 1) continue;              // chỉ lấy phần tử lá
                    const t = (e.textContent || '').trim().toLowerCase();
                    if (!(t in EX)) continue;                          // phải khớp CHÍNH XÁC
                    const r = e.getBoundingClientRect();
                    if (r.width <= 0 || r.height <= 0) continue;
                    const cy = r.top + r.height / 2;
                    if (Math.abs(cy - ycy) > 18) continue;             // cùng hàng ngang
                    if (r.left < yr.left) continue;                    // vai trò nằm bên phải tên
                    const a = r.width * r.height;
                    if (a < bestArea) { bestArea = a; best = EX[t]; }
                }
                return best;
            }""")
        except Exception:
            _my = ""
        if _my:
            log_fn(f"  [ADDQT] (quyền của tài khoản trên brand: {_my})")
        # ⚠ KHÔNG chặn cứng ở đây (đọc quyền có thể sai). Việc chặn dựa vào 'dropdown vai trò
        #   có option Owner hay không' ở bước sau — chính xác hơn nhiều.
        if _my == "manager":
            log_fn("  [ADDQT] ⚠ Có vẻ tài khoản chỉ là MANAGER — vẫn thử tiếp, sẽ kiểm tra lại "
                   "bằng danh sách vai trò thật.")

        # (4.6) Bấm icon 'Thêm người dùng' (góc phải trên hộp). Icon KHÔNG có chữ → bấm nút
        #       ICON-ONLY (bỏ nút DONE/Cancel có chữ) hoặc nút có aria-label add/invite/member.
        async def _add_dialog_showing() -> bool:
            try:
                if await page.locator('input:visible').count() > 0:
                    return True
            except Exception:
                pass
            for _t in ["email address", "địa chỉ email", "Add name", "Thêm tên",
                       "Add new user", "Thêm người dùng mới"]:
                try:
                    if await page.get_by_text(__re_v.compile(_t, __re_v.I)).count() > 0:
                        return True
                except Exception:
                    pass
            return False

        _add_open = False
        # Icon 'thêm người' KHÔNG phải <button> chuẩn → dùng JS click TRỰC TIẾP: tìm phần tử
        # clickable ở GÓC PHẢI-TRÊN hộp 'Manage permissions' (cùng hàng tiêu đề), bấm nó.
        for _attempt in range(4):
            try:
                _res = await page.evaluate(r"""() => {
                    const norm = s => (s||'').toLowerCase();
                    // 1) theo aria-label add/invite/member
                    let cand = [...document.querySelectorAll('[aria-label]')].find(e => {
                        const a = norm(e.getAttribute('aria-label'));
                        return /add|invite|member|người|thành viên|mời/.test(a)
                               && e.offsetParent !== null;
                    });
                    if (cand) { cand.click(); return 'aria:'+cand.getAttribute('aria-label'); }
                    // 2) tìm HỘP chứa 'Manage permissions' + 'Primary owner'
                    let dlg = null;
                    for (const d of document.querySelectorAll('div')) {
                        const t = d.textContent || '';
                        if ((t.indexOf('Manage permissions')>=0 || t.indexOf('Quản lý quyền')>=0)
                          && (t.indexOf('Primary owner')>=0 || t.indexOf('sở hữu chính')>=0)) {
                            if (!dlg || d.getBoundingClientRect().width < dlg.getBoundingClientRect().width)
                                dlg = d;
                        }
                    }
                    if (!dlg) return 'no-dialog';
                    const r = dlg.getBoundingClientRect();
                    // phần tử clickable ở HÀNG TIÊU ĐỀ (y gần đỉnh) và BÊN PHẢI
                    const cs = [...dlg.querySelectorAll('button,[role="button"],[jsaction],[data-tooltip]')]
                      .filter(e => {
                        const b = e.getBoundingClientRect();
                        return b.width>0 && b.height>0 && b.top < r.top + 80
                               && b.left > r.left + r.width*0.55;
                      });
                    cs.sort((a,b)=> b.getBoundingClientRect().left - a.getBoundingClientRect().left);
                    if (cs.length) { cs[0].click(); return 'topright'; }
                    return 'no-icon';
                }""")
                log_fn(f"  [ADDQT] (click add-icon: {_res})")
            except Exception:
                pass
            await page.wait_for_timeout(1500)
            if await _add_dialog_showing():
                _add_open = True
                break
        if not _add_open:
            try:
                await page.screenshot(path=_dbg_path("debug_addqt_owner.png"), timeout=5000)
            except Exception:
                pass
            return False, "", "Không mở được hộp 'Thêm người dùng mới' (xem debug_addqt_owner.png)"

        # (4.7) Điền email: tìm TỌA ĐỘ ô nhập rồi CLICK CHUỘT THẬT (page.mouse) + gõ keyboard.
        #       Ô là input/contenteditable tùy biến → click theo toạ độ là chắc nhất.
        async def _email_present() -> bool:
            try:
                if await page.get_by_text(owner_email).count() > 0:
                    return True
            except Exception:
                pass
            try:
                v = await page.evaluate(
                    "() => { const i=[...document.querySelectorAll('input,textarea')]"
                    ".find(x=>x.offsetParent&&x.value); return i? i.value : ''; }")
                if owner_email.lower() in (v or "").lower():
                    return True
            except Exception:
                pass
            return False

        _email_done = False
        for _try in range(3):
            _box = await page.evaluate(r"""() => {
                let cands = [...document.querySelectorAll(
                    'input, textarea, [contenteditable="true"], [contenteditable=""], [role="textbox"]')]
                    .filter(e => e.offsetParent !== null);
                let f = cands.find(e => /email|name|address|add names|tên|địa chỉ/i.test(
                    (e.placeholder||'') + ' ' + (e.getAttribute('aria-label')||'') + ' '
                    + (e.getAttribute('data-placeholder')||'') + ' ' + (e.textContent||'')));
                if (!f) f = cands[cands.length - 1];
                if (!f) return null;
                const r = f.getBoundingClientRect();
                if (r.width < 2 || r.height < 2) return null;
                return {x: r.x + Math.min(r.width/2, 60), y: r.y + r.height/2};
            }""")
            if _box:
                try:
                    await page.mouse.click(_box["x"], _box["y"])
                    await page.wait_for_timeout(400)
                    await page.keyboard.type(owner_email, delay=25)
                    await page.wait_for_timeout(1500)
                except Exception:
                    pass
                if await _email_present():
                    _email_done = True
                    break
            await page.wait_for_timeout(1000)
        if not _email_done:
            try:
                await page.screenshot(path=_dbg_path("debug_addqt_owner.png"), timeout=5000)
            except Exception:
                pass
            return False, "", "Không điền được email vào hộp 'Add new users'"
        log_fn(f"  [ADDQT] ✓ Đã điền email owner: {owner_email}")

        # (4.7b) CLICK RA NGOÀI ô (blur) để email thành CHIP & dropdown vai trò hiện ra.
        try:
            # click vào phần mô tả/tiêu đề hộp (điểm trung tính, không phải nút)
            _blur = page.get_by_text(__re_v.compile(
                r"Allow others to help|Add new users|Thêm người dùng mới|Cho phép người khác",
                __re_v.I))
            if await _blur.count() > 0 and await _blur.first.is_visible():
                await _blur.first.click(timeout=3000)
            else:
                # dự phòng: click 1 điểm trong hộp phía trên ô nhập
                _bx = await page.evaluate(r"""() => {
                    for (const d of document.querySelectorAll('div')) {
                        const t = d.textContent||'';
                        if (t.indexOf('Add new users')>=0 || t.indexOf('Thêm người dùng')>=0) {
                            const r = d.getBoundingClientRect();
                            if (r.width>150 && r.width<700)
                                return {x: r.x + r.width/2, y: r.y + 40};
                        }
                    }
                    return null;
                }""")
                if _bx:
                    await page.mouse.click(_bx["x"], _bx["y"])
        except Exception:
            pass
        await page.wait_for_timeout(1500)   # chờ chip + dropdown vai trò kích hoạt

        # (4.8→4.9) Chọn vai trò 'Owner' — THỬ NHIỀU CHIẾN LƯỢC cho tới khi chữ 'Choose a role'
        #           biến mất. Dropdown Google là phần tử tùy biến nên 1 cách hay trượt.
        _OPEN = ["choose a role", "chọn một vai trò", "select a role"]
        _OWNER = ["owner", "chủ sở hữu", "所有者", "소유자"]

        # ══ NHẬN DIỆN ĐÚNG DROPDOWN CỦA HỘP 'Add new users' ══
        # Trang có 2 dropdown giống hệt nhau (1 của user CŨ trong danh sách, 1 của hộp mới).
        # DẤU HIỆU DUY NHẤT: chỉ dropdown của HỘP mới có option 'Choose a role'.
        # ══════════════════════════════════════════════════════════════════
        #  CÁCH CHỌN 'Owner' — ĐÃ KIỂM CHỨNG TRỰC TIẾP TRÊN TRANG GOOGLE THẬT
        #  Trang có 3 NHÓM option giống nhau:
        #    A) dropdown của user CŨ           → cột x KHÁC  (vd x=1250)
        #    B) ô hiển thị giá trị của hộp     → cùng cột, CHỈ ô đang chọn cao 33, còn lại CAO 0
        #    C) menu ĐÃ BUNG của hộp          → cùng cột, các option đều CAO > 0  ← PHẢI CLICK CÁI NÀY
        #  ⇒ Quy tắc: option 'Owner' hợp lệ = CAO > 0  VÀ  CÙNG CỘT X với ô 'Choose a role'.
        # ══════════════════════════════════════════════════════════════════
        _JS_ROLE = r"""
            const _OPT = '[role="option"], div[jsname="wQNmvb"]';
            const _T = e => (e.textContent || '').trim().toLowerCase();
            const _OWN = ['owner','chủ sở hữu','所有者','소유자'];
            const _CHS = ['choose a role','chọn một vai trò','select a role'];
            // Cột X của ô vai trò TRONG HỘP (mốc = option 'Choose a role' — chỉ hộp mới có)
            function boxColX() {
                let x = null;
                for (const o of document.querySelectorAll(_OPT)) {
                    if (_CHS.indexOf(_T(o)) < 0) continue;
                    const r = o.getBoundingClientRect();
                    if (r.height > 0) return r.left;        // ưu tiên ô đang hiển thị
                    if (x === null) x = r.left;             // dự phòng khi đã chọn xong
                }
                return x;
            }
            // Ô đang HIỂN THỊ giá trị vai trò của hộp (cao > 0, cùng cột, aria-selected=true)
            function boxShown() {
                const x = boxColX(); if (x === null) return null;
                for (const o of document.querySelectorAll(_OPT)) {
                    const r = o.getBoundingClientRect();
                    if (r.height <= 0) continue;
                    if (Math.abs(r.left - x) > 60) continue;
                    if (o.getAttribute('aria-selected') !== 'true') continue;
                    return o;
                }
                return null;
            }
            // Option 'Owner' trong MENU ĐANG BUNG của hộp (cao > 0 + cùng cột + không phải ô hiển thị)
            function boxOwnerOpen() {
                const x = boxColX(); if (x === null) return null;
                const shown = boxShown();
                for (const o of document.querySelectorAll(_OPT)) {
                    if (_OWN.indexOf(_T(o)) < 0) continue;
                    const r = o.getBoundingClientRect();
                    if (r.height <= 0) continue;              // ⚠ CAO 0 = menu chưa bung → bỏ
                    if (Math.abs(r.left - x) > 60) continue;  // ⚠ khác cột = dropdown user cũ → bỏ
                    if (o === shown) continue;
                    return o;
                }
                return null;
            }
        """

        async def _role_is_owner() -> bool:
            """Ô vai trò của HỘP đang hiển thị 'Owner' chưa (đã kiểm chứng trên trang thật)."""
            try:
                return await page.evaluate(_JS_ROLE + r"""
                (() => {
                    const s = boxShown();
                    return !!s && _OWN.indexOf(_T(s)) >= 0;
                })()""")
            except Exception:
                return False

        async def _pick_owner_real() -> bool:
            """Chọn 'Owner': bung menu (click ô hiển thị) → click option Owner CAO>0 cùng cột."""
            try:
                if await _role_is_owner():
                    return True
                # 1) Chưa thấy option Owner cao > 0 → menu chưa bung → CLICK ô hiển thị để bung
                need_open = await page.evaluate(_JS_ROLE + "(() => !boxOwnerOpen())()")
                if need_open:
                    pos = await page.evaluate(_JS_ROLE + r"""
                    (() => {
                        const s = boxShown(); if (!s) return null;
                        const r = s.getBoundingClientRect();
                        return {x: r.left + r.width/2, y: r.top + r.height/2};
                    })()""")
                    if not pos:
                        log_fn("  [ADDQT] (pick Owner: không thấy ô vai trò của hộp)")
                        return False
                    await page.mouse.click(pos["x"], pos["y"])      # click chuột THẬT → bung menu
                    await page.wait_for_timeout(900)
                # 2) Menu đã bung → click đúng option Owner (dùng .click() — đã kiểm chứng ăn)
                ok = await page.evaluate(_JS_ROLE + r"""
                (() => {
                    const t = boxOwnerOpen();
                    if (!t) return false;
                    try { t.click(); } catch (e) { return false; }
                    return true;
                })()""")
                if not ok:
                    log_fn("  [ADDQT] (pick Owner: menu chưa bung ra option Owner)")
                    return False
                await page.wait_for_timeout(900)
                return await _role_is_owner()
            except Exception:
                return False

        _JS_FIND_LB = r"""
            const _OPTSEL = '[role="option"], div[jsname="wQNmvb"]';
            function _txt(e) { return (e.textContent || '').trim().toLowerCase(); }
            // Option 'Choose a role' CHỈ tồn tại ở dropdown của hộp 'Add new users'
            function findChooseOpt() {
                for (const o of document.querySelectorAll(_OPTSEL)) {
                    const t = _txt(o);
                    if (t === 'choose a role' || t === 'chọn một vai trò' || t === 'select a role')
                        return o;
                }
                return null;
            }
            // Tìm option 'Owner' CÙNG DROPDOWN với 'Choose a role':
            // leo dần lên từ 'Choose a role', cấp NÀO chứa 'Owner' ĐẦU TIÊN thì đó là dropdown
            // của hộp (vì 'Choose a role' chỉ có ở dropdown hộp) → không đụng dropdown user cũ.
            function findBoxOwnerOpt() {
                const c = findChooseOpt();
                if (!c) return null;
                let node = c.parentElement;
                for (let k = 0; k < 5 && node; k++) {
                    for (const o of node.querySelectorAll(_OPTSEL)) {
                        const t = _txt(o);
                        if (t === 'owner' || t === 'chủ sở hữu' || t === '所有者' || t === '소유자')
                            return o;
                    }
                    node = node.parentElement;
                }
                return null;
            }
            function findBoxListbox() {
                const o = findBoxOwnerOpt();
                return o ? o.parentElement : null;
            }
        """

        async def _role_chosen_v2() -> bool:
            """ĐÃ chọn Owner chưa — đọc aria-selected TRONG ĐÚNG dropdown của hộp 'Add new users'."""
            try:
                return await page.evaluate(_JS_FIND_LB + r"""
                (() => {
                    const own = findBoxOwnerOpt();          // option 'Owner' CỦA HỘP
                    if (!own) return false;
                    // đã chọn khi CHÍNH option Owner của hộp có aria-selected = true
                    if (own.getAttribute('aria-selected') === 'true') return true;
                    // dự phòng: 'Choose a role' hết được chọn cũng nghĩa là đã chốt vai trò
                    const c = findChooseOpt();
                    if (c && c.getAttribute('aria-selected') === 'false'
                          && own.getAttribute('aria-selected') === 'true') return true;
                    return false;
                })()""")
            except Exception:
                return False

        async def _box_role_geom() -> dict:
            """Toạ độ ô vai trò (đang hiện) + option Owner của HỘP, kèm kích thước thật."""
            try:
                return await page.evaluate(_JS_FIND_LB + r"""
                (() => {
                    const c = findChooseOpt(), own = findBoxOwnerOpt();
                    const g = (e) => {
                        if (!e) return null;
                        const r = e.getBoundingClientRect();
                        return {x: r.left + r.width/2, y: r.top + r.height/2,
                                w: r.width, h: r.height,
                                sel: e.getAttribute('aria-selected')};
                    };
                    // ô đang HIỂN THỊ giá trị = option có aria-selected=true VÀ cao > 0
                    let shown = null;
                    for (const o of document.querySelectorAll(_OPTSEL)) {
                        if (o.getAttribute('aria-selected') !== 'true') continue;
                        const r = o.getBoundingClientRect();
                        if (r.height <= 0) continue;
                        const t = _txt(o);
                        if (t === 'choose a role' || t === 'chọn một vai trò'
                            || t === 'owner' || t === 'manager') {
                            // ưu tiên đúng ô của HỘP (cùng nhánh với 'Choose a role')
                            if (c && (o === c || o.parentElement === c.parentElement)) { shown = g(o); break; }
                            if (!shown) shown = g(o);
                        }
                    }
                    return {choose: g(c), owner: g(own), shown: shown};
                })()""") or {}
            except Exception:
                return {}

        async def _pick_owner_keyboard_v2() -> bool:
            """Chọn Owner bằng BÀN PHÍM trên đúng ô vai trò của HỘP.
            Danh sách kiểu 'listbox thu gọn' (option cao 0px) không click được → dùng phím:
            focus ô 'Choose a role' → ArrowDown (Choose a role → Owner) → Enter chốt."""
            try:
                await page.evaluate(_JS_FIND_LB + r"""
                (() => {
                    const c = findChooseOpt();
                    if (!c) return false;
                    try { c.scrollIntoView({block:'center'}); } catch(e) {}
                    try { c.focus(); } catch(e) {}
                    return true;
                })()""")
                await page.wait_for_timeout(400)
                # 'Choose a role' → ArrowDown 1 nhịp là tới 'Owner' (thứ tự DOM: choose, owner, manager)
                for _step in range(3):
                    await page.keyboard.press("ArrowDown")
                    await page.wait_for_timeout(600)
                    if await _role_chosen_v2():
                        log_fn(f"  [ADDQT] (pick Owner: bàn phím ArrowDown x{_step + 1})")
                        return True
                    # thử chốt bằng Enter rồi kiểm tra lại
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(600)
                    if await _role_chosen_v2():
                        log_fn(f"  [ADDQT] (pick Owner: bàn phím ArrowDown x{_step + 1} + Enter)")
                        return True
                return False
            except Exception:
                return False

        async def _open_menu_parent_v2() -> bool:
            """Mở menu bằng cách click phần tử CHA (container dropdown) — dự phòng khi
            click thẳng vào ô hiển thị không bung menu."""
            try:
                box = await page.evaluate(_JS_FIND_LB + r"""
                (() => {
                    const c = findChooseOpt();
                    if (!c) return null;
                    // leo lên tìm container có thể click (role listbox/combobox/button)
                    let n = c.parentElement;
                    for (let k = 0; k < 4 && n; k++) {
                        const role = (n.getAttribute && n.getAttribute('role')) || '';
                        const r = n.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 &&
                            (role === 'listbox' || role === 'combobox' || role === 'button'
                             || n.hasAttribute('aria-expanded'))) {
                            return {x: r.left + r.width/2, y: r.top + r.height/2};
                        }
                        n = n.parentElement;
                    }
                    return null;
                })()""")
                if not box:
                    return False
                await page.mouse.click(box["x"], box["y"])
                await page.wait_for_timeout(900)
                return True
            except Exception:
                return False

        async def _pick_owner_v2() -> bool:
            """Chọn 'Owner' trong hộp 'Add new users'.
            ⚠ MẤU CHỐT: option chỉ bấm được khi MENU ĐÃ BUNG (chiều cao > 0). Nếu Owner đang
            cao = 0 → menu chưa mở → phải CLICK vào ô đang hiện giá trị để bung menu trước."""
            try:
                g = await _box_role_geom()
                own = (g or {}).get("owner")
                shown = (g or {}).get("shown") or (g or {}).get("choose")
                # 1) Menu chưa bung (Owner cao = 0) → click ô đang hiện để MỞ menu
                if (not own) or own.get("h", 0) <= 0:
                    if not shown or shown.get("h", 0) <= 0:
                        log_fn("  [ADDQT] (pick Owner: không thấy ô vai trò)")
                        return False
                    await page.mouse.click(shown["x"], shown["y"])   # click chuột THẬT → bung menu
                    await page.wait_for_timeout(1000)
                    g = await _box_role_geom()
                    own = (g or {}).get("owner")
                # 2) Menu đã bung → click đúng option Owner
                if own and own.get("h", 0) > 0:
                    await page.mouse.click(own["x"], own["y"])
                    await page.wait_for_timeout(900)
                    log_fn("  [ADDQT] (pick Owner: click option sau khi bung menu)")
                    return await _role_chosen_v2()
                # 3) Menu vẫn chưa bung → thử click CONTAINER cha, rồi lại click Owner
                if await _open_menu_parent_v2():
                    g = await _box_role_geom()
                    own = (g or {}).get("owner")
                    if own and own.get("h", 0) > 0:
                        await page.mouse.click(own["x"], own["y"])
                        await page.wait_for_timeout(900)
                        log_fn("  [ADDQT] (pick Owner: click option sau khi mở bằng container)")
                        return await _role_chosen_v2()
                # 4) Cuối cùng: DÙNG BÀN PHÍM (listbox thu gọn chỉ đổi được bằng phím)
                if await _pick_owner_keyboard_v2():
                    return True
                log_fn(f"  [ADDQT] (pick Owner: menu chưa bung — Owner cao "
                       f"{(own or {}).get('h', '?')}px)")
                return False
            except Exception:
                return False

        async def _role_chosen() -> bool:
            """ĐÃ chọn vai trò Owner trong hộp 'Add new users' hay chưa.
            ⚠ CHỈ xét BÊN TRONG hộp 'Add new users' — vì brand có thể ĐÃ CÓ SẴN user vai trò
            'Owner' ở danh sách phía sau (quét cả trang sẽ báo nhầm là đã chọn).
            Dấu hiệu chắc chắn: hộp KHÔNG còn chữ 'Choose a role' và nút INVITE đã BẬT."""
            try:
                return await page.evaluate(r"""() => {
                    // 1) tìm HỘP 'Add new users' (phần tử nhỏ nhất chứa cả tiêu đề + nút INVITE)
                    let box = null, ba = 1e18;
                    for (const e of document.querySelectorAll('div, c-wiz, form')) {
                        if (e.offsetParent === null) continue;
                        const t = (e.innerText || '');
                        const tl = t.toLowerCase();
                        if ((tl.indexOf('add new users') < 0 && tl.indexOf('thêm người dùng') < 0)
                            || tl.indexOf('invite') < 0) continue;
                        const r = e.getBoundingClientRect();
                        const a = r.width * r.height;
                        if (a > 0 && a < ba) { ba = a; box = e; }
                    }
                    if (!box) return false;
                    const bt = (box.innerText || '').toLowerCase();
                    // 2) còn 'Choose a role' → CHƯA chọn (khi menu mở, option này vẫn hiện)
                    if (bt.indexOf('choose a role') >= 0 || bt.indexOf('chọn một vai trò') >= 0)
                        return false;
                    // 3) phải thấy 'Owner' (nếu lỡ chọn Manager thì hộp hiện 'Manager' → false)
                    const hasOwner = (bt.indexOf('owner') >= 0 || bt.indexOf('chủ sở hữu') >= 0);
                    if (!hasOwner) return false;
                    // 4) XÁC NHẬN CUỐI: nút INVITE đã BẬT (không disabled/xám)
                    for (const e of box.querySelectorAll('*')) {
                        if (e.offsetParent === null) continue;
                        const t = (e.textContent || '').trim().toLowerCase();
                        if (t !== 'invite' && t !== 'mời') continue;
                        let n = e;
                        for (let k = 0; k < 4 && n; k++) {
                            if (n.getAttribute && (n.getAttribute('aria-disabled') === 'true'
                                                   || n.hasAttribute('disabled'))) return false;
                            n = n.parentElement;
                        }
                        return true;   // thấy INVITE và không disabled → ĐÃ chọn xong vai trò
                    }
                    return true;
                }""")
            except Exception:
                return False

        async def _menu_open() -> bool:
            # Menu CỦA HỘP đang mở = trong listbox của hộp có ≥2 option HIỂN THỊ.
            # (Chỉ xét dropdown của hộp — dropdown user cũ không tính.)
            try:
                return await page.evaluate(_JS_FIND_LB + r"""
                (() => {
                    const lb = findBoxListbox();
                    if (!lb) return false;
                    let n = 0;
                    for (const o of lb.querySelectorAll('[role="option"], div[jsname="wQNmvb"]')) {
                        const r = o.getBoundingClientRect();
                        if (o.offsetParent !== null && r.width > 0 && r.height > 0) n++;
                    }
                    return n >= 2;
                })()""")
            except Exception:
                return False

        async def _open_dropdown():
            # Mở list bằng cách click TRIGGER (phần tử hiển thị giá trị, KHÔNG phải 1 option trong list).
            # ⚠ CHỈ tìm BÊN TRONG hộp 'Add new users' — tránh bấm nhầm ô vai trò của user ĐÃ CÓ SẴN
            #   trong danh sách 'Manage permissions' phía sau.
            try:
                box = await page.evaluate(r"""(words) => {
                    // khoanh vùng hộp 'Add new users' (nhỏ nhất chứa tiêu đề + INVITE)
                    let scope = null, ba = 1e18;
                    for (const e of document.querySelectorAll('div, c-wiz, form')) {
                        if (e.offsetParent === null) continue;
                        const tl = (e.innerText || '').toLowerCase();
                        if ((tl.indexOf('add new users') < 0 && tl.indexOf('thêm người dùng') < 0)
                            || tl.indexOf('invite') < 0) continue;
                        const r = e.getBoundingClientRect();
                        const a = r.width * r.height;
                        if (a > 0 && a < ba) { ba = a; scope = e; }
                    }
                    // ⚠ KHÔNG tìm thấy hộp → TRẢ VỀ null (KHÔNG quét cả trang), tránh bấm nhầm
                    //    ô vai trò của chính mình trong 'Manage permissions' → tự hạ quyền.
                    if (!scope) return null;
                    const root = scope;
                    for (const e of root.querySelectorAll('*')) {
                        if (e.offsetParent === null) continue;
                        if (e.getAttribute && e.getAttribute('role') === 'option') continue;
                        if (e.closest && e.closest('[role="option"]')) continue;
                        if (e.getAttribute && e.getAttribute('jsname') === 'wQNmvb') continue;
                        let t = (e.textContent||'').trim().toLowerCase();
                        t = t.replace('arrow_drop_down','').replace('arrow_downward','').trim();
                        if (t.indexOf('primary') >= 0) continue;
                        if (words.indexOf(t) >= 0 && e.children.length <= 4) {
                            const r = e.getBoundingClientRect();
                            if (r.width>0&&r.height>0) return {x:r.x+r.width/2,y:r.y+r.height/2};
                        }
                    } return null;
                }""", _OPEN + _OWNER + ["manager", "người quản lý"])
                if box:
                    await page.mouse.click(box["x"], box["y"])
                    await page.wait_for_timeout(900)
                    return True
            except Exception:
                pass
            return False

        async def _close_menu():
            # đóng list (không đổi lựa chọn) bằng cách click vào tiêu đề/mô tả hộp — để INVITE lộ ra.
            try:
                _t = page.get_by_text(__re_v.compile(
                    r"Add new users|Thêm người dùng mới", __re_v.I))
                if await _t.count() > 0 and await _t.first.is_visible():
                    await _t.first.click(timeout=2500)
                    await page.wait_for_timeout(500)
            except Exception:
                pass

        async def _pick_owner_playwright() -> bool:
            for _w in ["Owner", "Chủ sở hữu"]:
                try:
                    el = page.get_by_text(_w, exact=True)
                    nq = await el.count()
                    for i in range(min(nq, 8)):
                        it = el.nth(i)
                        _t = ((await it.inner_text()) or "").strip().lower()
                        if "primary" in _t or "manager" in _t or "quản lý" in _t or "chính" in _t:
                            continue
                        if await it.is_visible():
                            await it.click(timeout=3000, force=True)
                            await page.wait_for_timeout(1000)
                            if await _role_chosen():
                                return True
                except Exception:
                    pass
            return False

        async def _pick_owner_coord() -> bool:
            try:
                box = await page.evaluate(r"""(words) => {
                    let best=null, ba=1e18;
                    for (const e of document.querySelectorAll('*')) {
                        if (e.offsetParent === null) continue;
                        const t=(e.textContent||'').trim().toLowerCase();
                        if (words.indexOf(t)<0 || e.children.length>3) continue;
                        const r=e.getBoundingClientRect(); const a=r.width*r.height;
                        if (r.width>0&&r.height>0&&a<ba){best={x:r.x+r.width/2,y:r.y+r.height/2};ba=a;}
                    } return best;
                }""", _OWNER)
                if box:
                    await page.mouse.click(box["x"], box["y"])
                    await page.wait_for_timeout(1000)
                    return await _role_chosen()
            except Exception:
                pass
            return False

        # Widget vai trò của Google: option = <div jsname="wQNmvb"> chứa <span>Owner</span>.
        # Click tọa độ chỉ HIGHLIGHT (aria-selected=true) nhưng KHÔNG chốt vì lớp ripple chặn.
        # → Bắn chuỗi sự kiện pointer/mouse THẲNG vào đúng div option (bỏ qua lớp phủ).
        async def _pick_owner_dispatch() -> bool:
            try:
                ok = await page.evaluate(r"""() => {
                    const wants = ['owner','chủ sở hữu','所有者','소유자'];
                    let target = null;
                    const cand = document.querySelectorAll(
                        'div[jsname="wQNmvb"], [role="option"], li[role="option"]');
                    for (const d of cand) {
                        const t = (d.textContent||'').trim().toLowerCase();
                        if (wants.indexOf(t) >= 0) { target = d; break; }
                    }
                    if (!target) return false;
                    try { target.scrollIntoView({block:'center'}); } catch(e){}
                    const r = target.getBoundingClientRect();
                    const o = {bubbles:true, cancelable:true, view:window,
                               clientX:r.left+r.width/2, clientY:r.top+r.height/2, button:0};
                    const seq = ['pointerover','pointerenter','mouseover','pointerdown',
                                 'mousedown','focus','pointerup','mouseup','click'];
                    for (const ty of seq) {
                        let ev;
                        try {
                            ev = ty.startsWith('pointer') ? new PointerEvent(ty,o)
                               : (ty==='focus' ? new FocusEvent(ty,{bubbles:true})
                                              : new MouseEvent(ty,o));
                        } catch(e) { ev = new MouseEvent(ty.replace('pointer','mouse'),o); }
                        try { target.dispatchEvent(ev); } catch(e){}
                    }
                    return true;
                }""")
                if ok:
                    await page.wait_for_timeout(900)
                    return await _role_chosen()
            except Exception:
                pass
            return False

        # Owner là option ACTIVE (tabindex=0, aria-selected=true) → focus rồi Enter/Space để CHỐT.
        async def _pick_owner_enter() -> bool:
            for _sel in ['div[jsname="wQNmvb"][aria-selected="true"]',
                         'div[jsname="wQNmvb"][tabindex="0"]',
                         '[role="option"][aria-selected="true"]']:
                try:
                    el = page.locator(_sel)
                    if await el.count() == 0:
                        continue
                    t = ((await el.first.inner_text()) or "").strip().lower()
                    if t not in ("owner", "chủ sở hữu", "所有者", "소유자"):
                        continue
                    await el.first.focus(timeout=2000)
                    for _k in ["Enter", " "]:
                        try:
                            await page.keyboard.press("Enter" if _k == "Enter" else "Space")
                            await page.wait_for_timeout(800)
                            if await _role_chosen():
                                return True
                        except Exception:
                            pass
                except Exception:
                    pass
            return False

        # ⚠⚠ AN TOÀN TUYỆT ĐỐI: chỉ click option NẰM TRONG khung hộp 'Add new users'.
        # (Trước đây các hàm pick quét CẢ TRANG → bấm nhầm ô vai trò của CHÍNH MÌNH trong danh
        #  sách 'Manage permissions' phía sau → TỰ HẠ QUYỀN Owner → Manager. Cấm tuyệt đối.)
        async def _pick_owner_in_box() -> bool:
            try:
                box = await page.evaluate(r"""(wants) => {
                    // 1) khung hộp 'Add new users'
                    let scope = null, ba = 1e18;
                    for (const e of document.querySelectorAll('div, c-wiz, form')) {
                        if (e.offsetParent === null) continue;
                        const tl = (e.innerText || '').toLowerCase();
                        if ((tl.indexOf('add new users') < 0 && tl.indexOf('thêm người dùng') < 0)
                            || tl.indexOf('invite') < 0) continue;
                        const r = e.getBoundingClientRect();
                        const a = r.width * r.height;
                        if (a > 0 && a < ba) { ba = a; scope = e; }
                    }
                    if (!scope) return null;
                    const R = scope.getBoundingClientRect();
                    // vùng hợp lệ = hộp (cho dropdown tràn xuống dưới tối đa 200px)
                    const okPos = (r) => {
                        const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
                        return cx >= R.left - 20 && cx <= R.right + 20
                            && cy >= R.top - 20  && cy <= R.bottom + 200;
                    };
                    // 2) tìm option 'Owner' HIỂN THỊ nằm trong vùng hợp lệ
                    for (const o of document.querySelectorAll('[role="option"], div[jsname="wQNmvb"]')) {
                        if (o.offsetParent === null) continue;      // phải đang hiện
                        const t = (o.textContent || '').trim().toLowerCase();
                        if (wants.indexOf(t) < 0) continue;          // đúng chữ 'Owner'
                        const r = o.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) continue;
                        if (!okPos(r)) continue;                     // ⚠ NGOÀI hộp → BỎ QUA
                        return {x: r.left + r.width / 2, y: r.top + r.height / 2};
                    }
                    return null;
                }""", ["owner", "chủ sở hữu", "所有者", "소유자"])
                if not box:
                    return False
                await page.mouse.click(box["x"], box["y"])   # click chuột THẬT, đúng toạ độ
                await page.wait_for_timeout(900)
                return await _role_chosen()
            except Exception:
                return False

        # Click thẳng vào DIV option (không phải span) bằng Playwright — nhắm đúng phần tử, bỏ overlay.
        async def _pick_owner_div() -> bool:
            for _sel in ['div[jsname="wQNmvb"]', '[role="option"]']:
                try:
                    loc = page.locator(_sel)
                    for i in range(min(await loc.count(), 8)):
                        el = loc.nth(i)
                        try:
                            t = ((await el.inner_text()) or "").strip().lower()
                        except Exception:
                            continue
                        if t not in ("owner", "chủ sở hữu", "所有者", "소유자"):
                            continue
                        try:
                            await el.scroll_into_view_if_needed(timeout=2000)
                        except Exception:
                            pass
                        await el.click(timeout=3000, force=True)
                        await page.wait_for_timeout(900)
                        if await _role_chosen():
                            return True
                except Exception:
                    pass
            return False

        # ── CHẨN ĐOÁN QUYỀN (làm TRƯỚC, tránh chạy mò rồi quá giờ) ─────────
        # Google CHỈ hiện lựa chọn 'Owner' nếu tài khoản đang đăng nhập là Owner/Primary owner.
        # Nếu tài khoản chỉ là 'Manager' → dropdown KHÔNG có 'Owner' → KHÔNG thể add chủ sở hữu.
        if not await _menu_open():
            await _open_dropdown()
            await page.wait_for_timeout(900)
        try:
            _roles = await page.evaluate(r"""() => {
                const out = [];
                for (const o of document.querySelectorAll('[role="option"], div[jsname="wQNmvb"]')) {
                    if (o.offsetParent === null) continue;
                    const t = (o.textContent || '').trim();
                    if (t && out.indexOf(t) < 0) out.push(t);
                }
                return out;
            }""")
        except Exception:
            _roles = []
        if _roles:
            log_fn(f"  [ADDQT] Vai trò có thể chọn: {' | '.join(_roles[:6])}")
        try:   # vai trò của CHÍNH tài khoản này trong brand (dòng 'You (...)')
            _my_role = await page.evaluate(r"""() => {
                const b = document.body ? (document.body.innerText || '') : '';
                const m = b.match(/You\s*\([^)]*\)\s*\n?\s*(Primary owner|Owner|Manager)/i);
                return m ? m[1] : '';
            }""")
        except Exception:
            _my_role = ""
        if _my_role:
            log_fn(f"  [ADDQT] Quyền của tài khoản này trong brand: {_my_role}")
        _has_owner_opt = any(("owner" in (r or "").lower() and "primary" not in (r or "").lower())
                             for r in (_roles or []))
        if _roles and not _has_owner_opt:
            try:
                await page.screenshot(path=_dbg_path("debug_addqt_owner.png"), timeout=5000)
            except Exception:
                pass
            _mr = f" — quyền hiện tại: {_my_role}" if _my_role else ""
            log_fn(f"  [ADDQT] ✗ Danh sách vai trò KHÔNG có 'Owner'{_mr}.")
            return False, "", ("KHÔNG add được Chủ sở hữu: tài khoản này không đủ quyền"
                               f"{_mr}. Chỉ Owner/Primary owner mới add được Owner. "
                               f"Vai trò khả dụng: {', '.join(_roles[:5])}")

        # ⚠ CHỈ dùng _pick_owner_v2/_role_chosen_v2: chúng nhắm ĐÚNG dropdown của hộp
        #   'Add new users' (dropdown duy nhất có option 'Choose a role'), nên KHÔNG BAO GIỜ
        #   đụng tới ô vai trò của chính mình trong danh sách (từng gây tự hạ Owner→Manager).
        _role_ok = False
        for _try in range(6):
            # ⚙ DÙNG CÁCH ĐÃ KIỂM CHỨNG TRỰC TIẾP TRÊN TRANG GOOGLE THẬT
            if await _role_is_owner():
                _role_ok = True
                break
            if await _pick_owner_real():
                _role_ok = True
                break
            await page.wait_for_timeout(700)
            if await _role_is_owner():
                _role_ok = True
                break
            log_fn(f"  [ADDQT] (chọn vai trò Owner: chưa xong, lần {_try + 1}/6)")
            await page.wait_for_timeout(700)
        if _role_ok:
            log_fn("  [ADDQT] ✓ Đã chọn vai trò Owner")
            # đóng list (nếu còn mở) để nút INVITE lộ ra, KHÔNG đổi lựa chọn Owner
            if await _menu_open():
                await _close_menu()
                await page.wait_for_timeout(400)
        if not _role_ok:
            try:
                await page.screenshot(path=_dbg_path("debug_addqt_owner.png"), timeout=5000)
            except Exception:
                pass
            # DUMP DOM thật của ô vai trò để phân tích (không đoán nữa)
            try:
                _dom = await page.evaluate(_JS_FIND_LB + r"""(() => {
                    const out = [];
                    // ── CHẨN ĐOÁN: tìm được option Owner của HỘP không? trạng thái ra sao? ──
                    try {
                        const c = findChooseOpt(), own = findBoxOwnerOpt();
                        out.push('### CHAN DOAN ###');
                        out.push('findChooseOpt: ' + (c ? 'CO' : 'KHONG'));
                        if (c) {
                            const rc = c.getBoundingClientRect();
                            out.push('  choose aria-selected=' + c.getAttribute('aria-selected')
                                + ' visible=' + (c.offsetParent !== null)
                                + ' rect=' + Math.round(rc.left) + ',' + Math.round(rc.top)
                                + ' ' + Math.round(rc.width) + 'x' + Math.round(rc.height));
                        }
                        out.push('findBoxOwnerOpt: ' + (own ? 'CO' : 'KHONG'));
                        if (own) {
                            const ro = own.getBoundingClientRect();
                            out.push('  owner aria-selected=' + own.getAttribute('aria-selected')
                                + ' visible=' + (own.offsetParent !== null)
                                + ' rect=' + Math.round(ro.left) + ',' + Math.round(ro.top)
                                + ' ' + Math.round(ro.width) + 'x' + Math.round(ro.height)
                                + ' sameParentAsChoose=' + (c && own.parentElement === c.parentElement));
                        }
                        // đếm tổng số option 'Owner' trên trang
                        let nOwn = 0;
                        for (const o of document.querySelectorAll(_OPTSEL))
                            if (_txt(o) === 'owner') nOwn++;
                        out.push('tong so option "Owner" tren trang: ' + nOwn);
                        // CẤU TRÚC CHA của ô vai trò (tìm trigger mở menu thật)
                        if (c) {
                            let n = c.parentElement;
                            for (let k = 0; k < 5 && n; k++) {
                                const r = n.getBoundingClientRect();
                                out.push('  CHA[' + k + '] <' + n.tagName
                                    + '> role="' + ((n.getAttribute && n.getAttribute('role')) || '')
                                    + '" jsname="' + ((n.getAttribute && n.getAttribute('jsname')) || '')
                                    + '" aria-expanded="' + ((n.getAttribute && n.getAttribute('aria-expanded')) || '')
                                    + '" cls="' + String(n.className || '').slice(0, 60)
                                    + '" rect=' + Math.round(r.width) + 'x' + Math.round(r.height));
                                n = n.parentElement;
                            }
                        }
                        out.push('');
                    } catch (e) { out.push('chan doan loi: ' + e); }
                    document.querySelectorAll('select').forEach((s,i)=>{
                        out.push('=== SELECT#'+i+' visible='+(s.offsetParent!==null)
                            +' selIdx='+s.selectedIndex+' ===\n'+s.outerHTML.slice(0,900));
                    });
                    const seen = new Set();
                    for (const e of document.querySelectorAll('*')) {
                        const t=(e.textContent||'').trim().toLowerCase();
                        if ((t==='choose a role'||t==='owner'||t==='manager') && e.children.length<=2) {
                            const key = e.tagName+'|'+t+'|'+(e.className||'');
                            if (seen.has(key)) continue; seen.add(key);
                            out.push('=== EL <'+e.tagName+'> role="'+(e.getAttribute('role')||'')
                                +'" aria-selected="'+(e.getAttribute('aria-selected')||'')
                                +'" cls="'+String(e.className||'').slice(0,90)+'" text='
                                +JSON.stringify((e.textContent||'').trim().slice(0,30))+' ===\n'
                                +'PARENT<'+(e.parentElement?e.parentElement.tagName:'')+' role="'
                                +(e.parentElement?(e.parentElement.getAttribute('role')||''):'')+'">\n'
                                +e.outerHTML.slice(0,400));
                        }
                    }
                    return out.join('\n\n');
                })()""")
                with open(_dbg_path("debug_addqt_dom.txt"), "w", encoding="utf-8") as _f:
                    _f.write(_dom or "(không tìm thấy phần tử vai trò)")
            except Exception:
                pass
            return False, "", ("Không chọn được vai trò 'Owner' "
                               "(xem debug_addqt_owner.png + debug_addqt_dom.txt)")
        await page.wait_for_timeout(1000)

        # (4.10) Bấm 'Invite / Mời'. Owner đã chọn xong → CHỈ cần bấm INVITE.
        #         Nút INVITE của Google là <span>INVITE</span> trong div role=button —
        #         thử NHIỀU cách: role=button, get_by_text, JS .click(), rồi click toạ độ.
        _INV = ["invite", "mời", "邀请", "초대"]

        async def _click_invite_role() -> bool:
            for _w in ["Invite", "Mời"]:
                try:
                    b = page.get_by_role("button", name=__re_v.compile(rf"^\s*{_w}\s*$", __re_v.I))
                    if await b.count() > 0 and await b.first.is_visible():
                        await b.first.click(timeout=4000)
                        return True
                except Exception:
                    pass
            return False

        async def _click_invite_text() -> bool:
            for _iv in [r"^\s*Invite\s*$", r"^\s*Mời\s*$", r"^\s*邀请\s*$", r"^\s*초대\s*$"]:
                try:
                    b = page.get_by_text(__re_v.compile(_iv, __re_v.I))
                    for i in range(min(await b.count(), 5)):
                        el = b.nth(i)
                        if await el.is_visible():
                            await el.click(timeout=4000, force=True)
                            return True
                except Exception:
                    pass
            return False

        async def _click_invite_js() -> bool:
            # tìm phần tử text == INVITE, KHÔNG bị disable, rồi .click() thẳng + trả toạ độ
            try:
                box = await page.evaluate(r"""(words) => {
                    for (const e of document.querySelectorAll('*')) {
                        if (e.offsetParent === null) continue;
                        const t = (e.textContent||'').trim().toLowerCase();
                        if (words.indexOf(t) < 0 || e.children.length > 3) continue;
                        // bỏ qua nút CANCEL
                        if (t.indexOf('cancel')>=0 || t.indexOf('hủy')>=0) continue;
                        const dis = e.getAttribute && (e.getAttribute('aria-disabled')==='true');
                        if (dis) continue;
                        // click chính nó và cha (thường cha là role=button)
                        let clk = e; for (let k=0;k<3 && clk;k++){ try{clk.click();}catch(_){} clk = clk.parentElement; }
                        const r = e.getBoundingClientRect();
                        if (r.width>0 && r.height>0) return {x:r.x+r.width/2, y:r.y+r.height/2};
                    }
                    return null;
                }""", _INV)
                if box:
                    await page.wait_for_timeout(500)
                    return True
            except Exception:
                pass
            return False

        async def _click_invite_coord() -> bool:
            try:
                box = await page.evaluate(r"""(words) => {
                    for (const e of document.querySelectorAll('*')) {
                        if (e.offsetParent === null) continue;
                        const t = (e.textContent||'').trim().toLowerCase();
                        if (words.indexOf(t) < 0 || e.children.length > 3) continue;
                        if (t.indexOf('cancel')>=0 || t.indexOf('hủy')>=0) continue;
                        const r = e.getBoundingClientRect();
                        if (r.width>0 && r.height>0) return {x:r.x+r.width/2, y:r.y+r.height/2};
                    }
                    return null;
                }""", _INV)
                if box:
                    await page.mouse.click(box["x"], box["y"])
                    await page.wait_for_timeout(800)
                    return True
            except Exception:
                pass
            return False

        async def _click_invite_real() -> bool:
            """Bấm INVITE — ĐÚNG CÁCH ĐÃ KIỂM CHỨNG TRÊN TRANG GOOGLE THẬT:
            tìm phần tử text 'invite' đang HIỆN, KHÔNG disabled (xét cả 4 cấp cha) → .click()."""
            try:
                return await page.evaluate(r"""() => {
                    for (const e of document.querySelectorAll('*')) {
                        if (e.offsetParent === null) continue;
                        const t = (e.textContent || '').trim().toLowerCase();
                        if (t !== 'invite' && t !== 'mời') continue;
                        if (e.children.length > 3) continue;
                        let dis = false, n = e;
                        for (let k = 0; k < 4 && n; k++) {
                            if (n.getAttribute && (n.getAttribute('aria-disabled') === 'true'
                                                   || n.hasAttribute('disabled'))) { dis = true; break; }
                            n = n.parentElement;
                        }
                        if (dis) continue;               // nút còn xám → bỏ
                        try { e.click(); } catch (err) { continue; }
                        return true;
                    }
                    return false;
                }""")
            except Exception:
                return False

        _inv_ok = False
        for _try in range(4):
            if (await _click_invite_real() or await _click_invite_role()
                    or await _click_invite_text()
                    or await _click_invite_js() or await _click_invite_coord()):
                _inv_ok = True
                # xác nhận hộp 'Add new users' đã đóng (INVITE ăn) — nếu còn thì thử lại
                await page.wait_for_timeout(1500)
                try:
                    _still = await page.evaluate(
                        "() => (document.body.innerText||'').toLowerCase().indexOf('add new users')>=0"
                        " || (document.body.innerText||'').toLowerCase().indexOf('thêm người dùng')>=0")
                except Exception:
                    _still = False
                if not _still:
                    break   # hộp đã đóng → INVITE thành công
                _inv_ok = False   # còn hộp → chưa ăn, thử tiếp
            log_fn(f"  [ADDQT] (bấm INVITE: chưa ăn, lần {_try + 1}/4)")
            await page.wait_for_timeout(1200)
        if not _inv_ok:
            try:
                await page.screenshot(path=_dbg_path("debug_addqt_owner.png"), timeout=5000)
            except Exception:
                pass
            return False, "", "Không bấm được nút 'Mời/Invite' (xem debug_addqt_owner.png)"
        log_fn("  [ADDQT] ✓ Bấm Invite")
        await page.wait_for_timeout(3000)

        # (4.11→4.12) XÁC MINH: trong hộp phải hiện dòng email owner với vai trò owner (đã mời)
        _verified = False
        try:
            _dtxt = ""
            for _sel in ('div[role="dialog"]', 'tp-yt-paper-dialog', 'c-wiz'):
                try:
                    d = page.locator(_sel)
                    if await d.count() > 0:
                        _dtxt = (await d.last.inner_text()) or ""
                        if _dtxt:
                            break
                except Exception:
                    pass
            _low = _dtxt.lower()
            if owner_email.lower() in _low and any(
                    k in _low for k in ["invite", "mời", "owner", "chủ sở hữu"]):
                _verified = True
        except Exception:
            pass
        if not _verified:
            # đọc lại toàn trang
            try:
                _pg = (await page.content()).lower()
                if owner_email.lower() in _pg:
                    _verified = True
            except Exception:
                pass

        # (4.13) Bấm 'DONE' để đóng hộp 'Manage permissions' → hoàn tất.
        async def _click_done() -> bool:
            # thử nút DONE / Xong (get_by_role → get_by_text → JS click → toạ độ)
            for _w in ["Done", "Xong"]:
                try:
                    b = page.get_by_role("button", name=__re_v.compile(rf"^\s*{_w}\s*$", __re_v.I))
                    if await b.count() > 0 and await b.first.is_visible():
                        await b.first.click(timeout=4000)
                        return True
                except Exception:
                    pass
            for _dw in [r"^\s*Done\s*$", r"^\s*Xong\s*$", r"^\s*完成\s*$", r"^\s*완료\s*$"]:
                try:
                    b = page.get_by_text(__re_v.compile(_dw, __re_v.I))
                    for i in range(min(await b.count(), 5)):
                        el = b.nth(i)
                        if await el.is_visible():
                            await el.click(timeout=4000, force=True)
                            return True
                except Exception:
                    pass
            try:
                box = await page.evaluate(r"""(words) => {
                    for (const e of document.querySelectorAll('*')) {
                        if (e.offsetParent === null) continue;
                        const t = (e.textContent||'').trim().toLowerCase();
                        if (words.indexOf(t) < 0 || e.children.length > 3) continue;
                        let clk=e; for(let k=0;k<3&&clk;k++){try{clk.click();}catch(_){}clk=clk.parentElement;}
                        const r = e.getBoundingClientRect();
                        if (r.width>0&&r.height>0) return {x:r.x+r.width/2,y:r.y+r.height/2};
                    } return null;
                }""", ["done", "xong", "完成", "완료"])
                if box:
                    await page.mouse.click(box["x"], box["y"])
                    await page.wait_for_timeout(600)
                    return True
            except Exception:
                pass
            return False

        _done_ok = False
        for _dt in range(3):
            if await _click_done():
                await page.wait_for_timeout(1200)
                # DONE ăn khi hộp 'Manage permissions' đã đóng
                try:
                    _mp = await page.evaluate(
                        "() => (document.body.innerText||'').toLowerCase().indexOf('manage permissions')>=0")
                except Exception:
                    _mp = False
                if not _mp:
                    _done_ok = True
                    break
            await page.wait_for_timeout(800)
        if _done_ok:
            log_fn("  [ADDQT] ✓ Bấm DONE — đã đóng hộp")
        else:
            log_fn("  [ADDQT] (ⓘ đã mời owner, nhưng chưa xác nhận đóng được hộp DONE)")

        # (4.14) Đợi 5s → MỞ LẠI 'Manage permissions' → KIỂM TRA email đã được add owner chưa.
        log_fn("  [ADDQT] ⏳ Đợi 5s rồi mở lại Manage permissions để kiểm tra…")
        await page.wait_for_timeout(5000)
        _recheck = ""   # "" chưa rõ | "OK" thấy owner | "NO" không thấy
        try:
            _reopened = False
            # KHÔNG tải lại trang (tránh phải nhập 2FA lại). Sau DONE vẫn đang ở trang brand,
            # phiên vừa xác thực → chỉ cần BẤM LẠI 'Manage Permissions' để mở hộp, thường KHÔNG hỏi 2FA.
            if await _dialog_open():
                _reopened = True
            else:
                await _click_manage()
                _did_auth = False
                for _ in range(30):   # dò tối đa ~30s
                    await page.wait_for_timeout(1000)
                    if await _dialog_open():
                        _reopened = True
                        break
                    if await _cant_verify():
                        log_fn("  [ADDQT] (ⓘ Google chặn 'We couldn't verify' khi mở lại — bỏ qua kiểm tra)")
                        break
                    # Hiếm khi bị hỏi lại (vì không reload). Nếu có → re-auth ĐÚNG 1 lần rồi bấm lại.
                    if "accounts.google.com" in (page.url or "") and not _did_auth:
                        await _reauth_pw_2fa()
                        _did_auth = True
                        await page.wait_for_timeout(2500)
                        if not await _dialog_open():
                            await _click_manage()
            if _reopened:
                await page.wait_for_timeout(1500)
                _dtxt2 = ""
                for _sel in ('div[role="dialog"]', 'tp-yt-paper-dialog', 'c-wiz', 'body'):
                    try:
                        d = page.locator(_sel)
                        if await d.count() > 0:
                            _dtxt2 = (await d.last.inner_text()) or ""
                            if owner_email.lower() in _dtxt2.lower():
                                break
                    except Exception:
                        pass
                if owner_email.lower() in _dtxt2.lower():
                    _recheck = "OK"
                    log_fn(f"  [ADDQT] ✅ KIỂM TRA LẠI: '{owner_email}' ĐÃ có trong Manage permissions.")
                else:
                    _recheck = "NO"
                    log_fn(f"  [ADDQT] ⚠ KIỂM TRA LẠI: KHÔNG thấy '{owner_email}' trong danh sách!")
                    try:
                        await page.screenshot(path=_dbg_path("debug_addqt_recheck.png"), timeout=5000)
                    except Exception:
                        pass
            else:
                log_fn("  [ADDQT] (ⓘ không mở lại được hộp để kiểm tra — invite đã gửi trước đó)")
        except Exception:
            pass

        _pre = ("đã có sẵn kênh TH" if _has_brand else "đã tạo+chuyển kênh")
        if _recheck == "OK":
            log_fn(f"  [ADDQT] ✅ Đã add owner '{owner_email}' (đã kiểm tra lại: có trong danh sách).")
            return True, "", f"Add QT TH OK ({_pre}, owner {owner_email} — đã kiểm tra lại: CÓ)"
        if _recheck == "NO":
            log_fn(f"  [ADDQT] ⚠ Đã mời owner nhưng mở lại KHÔNG thấy '{owner_email}'.")
            return True, "", (f"Add QT TH: đã mời owner {owner_email} nhưng KIỂM TRA LẠI không thấy "
                              "(xem debug_addqt_recheck.png)")
        if _verified:
            log_fn(f"  [ADDQT] ✅ Đã add owner '{owner_email}' (đã mời, Chủ sở hữu).")
            return True, "", f"Add QT TH OK ({_pre}, đã mời owner {owner_email})"
        try:
            await page.screenshot(path=_dbg_path("debug_addqt_owner.png"), timeout=5000)
        except Exception:
            pass
        return False, "", ("Đã bấm Mời nhưng KHÔNG thấy owner trong danh sách "
                           "(xem debug_addqt_owner.png)")


async def do_change_banner(ws_url: str, email: str = "", banner_dir: str = "",
                           log_fn=print) -> tuple[bool, str, str]:
    """Thay ẢNH BÌA (banner) kênh YouTube bằng 1 ảnh ngẫu nhiên trong banner_dir.
    Flow: Studio → chọn kênh brand (thứ 2) → trang tùy chỉnh (EN) → Upload ảnh → Done → Publish.
    Trả về: (success, "", message)."""
    import os as _os
    banner = _pick_random_banner(banner_dir)
    if not banner:
        return False, "", f"Không có ảnh bìa trong thư mục: {banner_dir}"
    _fname = _os.path.basename(banner)

    async with async_playwright() as p:
        log_fn("  [BÌA] Kết nối browser…")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        # ÉP NGÔN NGỮ TIẾNG ANH cho YouTube/Studio qua cookie PREF (studio.youtube.com BỎ QUA
        # ?hl=en sau khi switch account → set cookie để mọi trang Studio load tiếng Anh, nút
        # Upload/Done/Publish khớp chuẩn, không dính tiếng Thái/ngôn ngữ account.
        try:
            await ctx.add_cookies([
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".youtube.com", "path": "/"},
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".google.com", "path": "/"},
            ])
        except Exception:
            pass
        page = await ctx.new_page()

        # (a) ĐỔI NGÔN NGỮ tài khoản sang English (US) QUA UI YouTube (lưu server-side →
        #     Studio kế thừa English). Đây là bước bạn yêu cầu — chắc hơn ?hl=en/cookie.
        log_fn("  [BÌA] Mở YouTube & đổi ngôn ngữ sang English (US)…")
        await _set_youtube_language_english(page, log_fn)

        # (b) Vào Studio → nếu hỏi chọn kênh thì chọn kênh brand (thứ 2)
        log_fn("  [BÌA] Mở YouTube Studio…")
        try:
            await page.goto("https://studio.youtube.com/?hl=en",
                            wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        await _dismiss_studio_popups(page, log_fn)   # đóng 'Welcome to YouTube Studio' (Continue)
        # Kênh ĐANG mở trong Studio (thường là kênh ĐẦU / kênh cá nhân)
        cur_cid = await _extract_channel_id(page)

        # CÁCH 1 (CHÍNH): lấy kênh thứ 2 qua trang channel_switcher — không click menu.
        brand_cid = await _brand_channel_id_via_switcher(page, cur_cid, log_fn)
        if brand_cid:
            log_fn(f"  [BÌA] ✓ Kênh thứ 2 (brand): {brand_cid}")
        else:
            # CÁCH 2 (DỰ PHÒNG): avatar → Switch account → kênh dưới.
            log_fn("  [BÌA] channel_switcher không ra kênh 2 → thử Switch account…")
            try:
                await page.goto("https://studio.youtube.com/?hl=en",
                                wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2000)
            except Exception:
                pass
            await _dismiss_studio_popups(page, log_fn)
            brand_cid = await _switch_to_second_channel(page, log_fn)
            if brand_cid == "FAIL":
                return False, "", ("Không chuyển được sang kênh thứ 2 (brand) — dừng để tránh "
                                   "đổi nhầm bìa kênh đầu. Xem debug_select_channel.png")

        await _dismiss_studio_popups(page, log_fn)
        # cid = kênh brand nếu tìm được; nếu account chỉ 1 kênh thì dùng kênh hiện tại.
        cid = brand_cid or cur_cid or await _extract_channel_id(page)
        for _ in range(4):
            if cid:
                break
            await page.wait_for_timeout(2000)
            cid = await _extract_channel_id(page)
        if not cid:
            _dead = await _channel_dead_reason(page)
            if _dead:
                return False, "KÊNH DIE", f"KÊNH DIE ({_dead})"
            return False, "", "Không lấy được channel ID (chưa có kênh?)"

        # (c) Mở trang tùy chỉnh kênh (branding) tiếng Anh
        log_fn("  [BÌA] Mở trang tùy chỉnh (Customization)…")
        try:
            await page.goto(f"https://studio.youtube.com/channel/{cid}/editing/images?hl=en",
                            wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        await _dismiss_studio_popups(page, log_fn)   # 'Welcome to YouTube Studio' có thể hiện ở đây

        # (c1) CHỜ KHỐI ẢNH BÌA RENDER XONG — trước đây chỉ chờ CỨNG 3.5s nên qua proxy chậm
        #      Studio chưa vẽ xong -> tưởng "không có nút Upload" rồi bỏ qua. Giờ dò tới 40s:
        #      sẵn sàng khi có input[type=file] HOẶC thấy tiêu đề 'Banner image'.
        _ready = False
        for _i in range(40):
            try:
                if await page.locator('input[type="file"]').count() > 0:
                    _ready = True
                if not _ready:
                    for _t in ["Banner image", "Ảnh bìa", "ภาพแบนเนอร์"]:
                        if await page.get_by_text(_re.compile(_t, _re.I)).count() > 0:
                            _ready = True
                            break
            except Exception:
                pass
            if _ready:
                break
            await page.wait_for_timeout(1000)
            if _i in (10, 20, 30):
                await _dismiss_studio_popups(page, log_fn)
        if _ready:
            await page.wait_for_timeout(1500)      # thêm nhịp cho nút vẽ xong
            log_fn(f"  [BÌA] Trang tùy chỉnh đã sẵn sàng (sau ~{_i + 1}s).")
        else:
            log_fn("  [BÌA] ⚠ Chờ 40s trang tùy chỉnh vẫn chưa render xong (mạng chậm?).")

        # (c2) XÁC MINH đã vào ĐÚNG trang tùy chỉnh của ĐÚNG kênh — nếu channel id sai/không
        #      thuộc account, Studio đá về dashboard/lỗi. KHÔNG được đi tiếp rồi báo thành công.
        # Studio mới redirect /editing/images → /editing/profile (tab 'Profile' chứa mục
        # 'Banner image'). Chấp nhận MỌI /editing/… miễn ĐÚNG channel id.
        _u_now = page.url or ""
        if cid not in _u_now or "/editing/" not in _u_now:
            try:
                await page.screenshot(path=_dbg_path("debug_banner_page.png"), timeout=5000)
            except Exception:
                pass
            log_fn(f"  [BÌA] ⚠ Không vào được trang tùy chỉnh của kênh {cid}. url={_u_now[:70]}")
            return False, "", (f"Không mở được trang tùy chỉnh kênh {cid} "
                               f"(kênh sai hoặc không có quyền). Xem debug_banner_page.png")

        # (d) Upload ảnh bìa — ưu tiên bấm nút Upload/Change (banner là nút ĐẦU TIÊN) rồi bắt
        #     hộp chọn file; nếu không được thì set thẳng vào input file đầu tiên.
        # QUAN TRỌNG: mục 'Banner image' dùng nút 'Upload'; mục 'Picture' (ảnh đại diện)
        # dùng 'Change'/'Remove'. PHẢI ưu tiên đúng nút Upload trong khối Banner, tránh
        # đổi nhầm ảnh đại diện.
        # NGUYÊN TẮC AN TOÀN: LUÔN khoanh vùng khối 'Banner image' TRƯỚC rồi mới bấm nút bên
        # trong nó — bất kể nút ghi 'Upload' (kênh CHƯA có bìa) hay 'Change' (kênh ĐÃ có bìa).
        # TUYỆT ĐỐI không dò chữ 'Change' trên toàn trang, vì khối 'Picture' (avatar) cũng có
        # nút 'Change' → sẽ đổi nhầm ảnh đại diện.
        _did = False
        _BANNER_TXT = ["Banner image", "Ảnh bìa", "ภาพแบนเนอร์"]
        _BTN_TXT = ["Upload", "Change", "Tải lên", "Thay đổi",
                    "อัปโหลด", "เปลี่ยน", "上傳", "上传", "アップロード", "변경"]

        async def _try_section(sec):
            """Trong 1 khối: ưu tiên set thẳng input[type=file]; nếu không có thì bấm nút
            (Upload/Change đều được) để bắt hộp chọn file. Trả True nếu đã đưa được ảnh."""
            nonlocal _did
            # (1) set thẳng input file trong khối — chắc nhất, không phụ thuộc chữ trên nút
            try:
                finp = sec.locator('input[type="file"]')
                if await finp.count() > 0:
                    await finp.first.set_input_files(banner)
                    return True
            except Exception:
                pass
            # (2) bấm nút trong khối (Upload hoặc Change) → hộp chọn file
            for _t in _BTN_TXT:
                try:
                    b = sec.locator(f'button:has-text("{_t}"), ytcp-button:has-text("{_t}"), '
                                    f'[role="button"]:has-text("{_t}")')
                    if await b.count() > 0 and await b.first.is_visible():
                        async with page.expect_file_chooser(timeout=8000) as _fc:
                            await b.first.click(timeout=3000)
                        chooser = await _fc.value
                        await chooser.set_files(banner)
                        return True
                except Exception:
                    pass
            # (3) nút bất kỳ trong khối (phòng khi ngôn ngữ lạ)
            try:
                b = sec.locator('button, ytcp-button, [role="button"]')
                if await b.count() > 0 and await b.first.is_visible():
                    async with page.expect_file_chooser(timeout=8000) as _fc:
                        await b.first.click(timeout=3000)
                    chooser = await _fc.value
                    await chooser.set_files(banner)
                    return True
            except Exception:
                pass
            return False

        # (d1) Khối chứa TIÊU ĐỀ 'Banner image' — cách nhắm chính xác nhất
        for _sec_txt in _BANNER_TXT:
            if _did:
                break
            for _sel in (f'ytcp-form-file-picker:has-text("{_sec_txt}")',
                         f'div:has(> h2:has-text("{_sec_txt}"))',
                         f'div:has(> h3:has-text("{_sec_txt}"))',
                         '[id*="banner" i]'):
                try:
                    sec = page.locator(_sel)
                    if await sec.count() > 0 and await _try_section(sec.first):
                        _did = True
                        log_fn(f"  [BÌA] ✓ Đưa ảnh vào khối '{_sec_txt}': {_fname}")
                        break
                except Exception:
                    pass

        # (d2) Dự phòng: khối ảnh bìa là ytcp-form-file-picker ĐẦU TIÊN (Banner nằm TRÊN Picture)
        if not _did:
            try:
                pickers = page.locator('ytcp-form-file-picker')
                if await pickers.count() >= 1 and await _try_section(pickers.first):
                    _did = True
                    log_fn(f"  [BÌA] ✓ Đưa ảnh vào khối ảnh bìa (picker đầu trang): {_fname}")
            except Exception:
                pass

        # (d3) Dự phòng cuối: input[type=file] ĐẦU TIÊN của trang — trên trang tùy chỉnh,
        #      khối Banner luôn đứng TRƯỚC khối Picture nên input đầu tiên là của ảnh bìa.
        if not _did:
            try:
                finp = page.locator('input[type="file"]')
                if await finp.count() > 0:
                    await finp.first.set_input_files(banner)
                    _did = True
                    log_fn(f"  [BÌA] ✓ Đưa ảnh vào input file đầu trang (ảnh bìa): {_fname}")
            except Exception:
                pass

        if not _did:
            try:
                await page.screenshot(path=_dbg_path("debug_banner_page.png"), timeout=5000)
            except Exception:
                pass
            return False, "", ("Không đưa được ảnh vào khối ảnh bìa "
                               "(xem debug_banner_page.png)")

        async def _click_btn(txts, timeout_ms=3000) -> bool:
            for t in txts:
                try:
                    b = page.locator(f'ytcp-button:has-text("{t}"), button:has-text("{t}"), '
                                     f'tp-yt-paper-button:has-text("{t}"), [role="button"]:has-text("{t}")')
                    n = await b.count()
                    for i in range(min(n, 4)):
                        el = b.nth(i)
                        try:
                            if await el.is_visible():
                                await el.click(timeout=timeout_ms)
                                return True
                        except Exception:
                            pass
                except Exception:
                    pass
            return False

        # (e) CHỜ hộp crop hiện rồi bấm Done — THEO CẤU TRÚC (không phụ thuộc ngôn ngữ):
        #     nút chính/confirm; nếu không có thì nút HÀNH ĐỘNG PHẢI-CÙNG của hộp (Cancel ở
        #     trái, Done ở phải). Chữ chỉ là dự phòng cuối.
        async def _visible_click(loc, timeout_ms=3000) -> bool:
            try:
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click(timeout=timeout_ms)
                    return True
            except Exception:
                pass
            return False

        async def _click_crop_done() -> bool:
            dlg = page.locator('tp-yt-paper-dialog[opened], ytcp-dialog, '
                               'ytcp-uploads-dialog, div[role="dialog"]')
            if await dlg.count() == 0:
                return False
            d = dlg.last
            # 1) nút chính/confirm theo id/kiểu (Studio)
            for sel in ['#done-button', '#confirm-button', '#save-button',
                        'ytcp-button[type="primary"]', 'ytcp-button.primary',
                        '[id*="done"]', '[id*="confirm"]']:
                if await _visible_click(d.locator(sel)):
                    return True
            # 2) nút HÀNH ĐỘNG cuối (phải-cùng) trong hộp = Done (Cancel ở trái).
            #    CHỈ xét ytcp-button/paper-button (nút CÓ NHÃN) → bỏ nút icon chọn thiết bị.
            #    Bỏ luôn nút có aria-label/text kiểu Cancel/Close để không bấm nhầm.
            try:
                btns = d.locator('ytcp-button, tp-yt-paper-button')
                keep = []
                n = await btns.count()
                for i in range(n):
                    b = btns.nth(i)
                    try:
                        if not await b.is_visible():
                            continue
                        _t = ((await b.get_attribute("aria-label") or "") + " " +
                              (await b.inner_text() or "")).lower()
                        if any(c in _t for c in ["cancel", "hủy", "huỷ", "close", "đóng",
                                                 "ยกเลิก", "取消", "취소", "abbrechen"]):
                            continue
                        keep.append(i)
                    except Exception:
                        pass
                if keep and await _visible_click(btns.nth(keep[-1])):
                    return True
            except Exception:
                pass
            # 3) dự phòng cuối: theo chữ (vài ngôn ngữ phổ biến)
            return await _click_btn(["Done", "Xong", "เสร็จ", "완료", "完成", "OK"])

        _done = False
        for _ in range(15):
            await page.wait_for_timeout(1000)
            if await _click_crop_done():
                log_fn("  [BÌA] ✓ Bấm Done (crop, theo cấu trúc)")
                _done = True
                break
        await page.wait_for_timeout(1500)
        await _dismiss_studio_popups(page, log_fn)

        # (f) CHỜ nút Publish BẬT rồi bấm (dò tối đa ~14s)
        _pub_txt = ["Publish", "Xuất bản", "เผยแพร่", "게시", "發布", "发布", "公開", "Veröffentlichen", "Publicar"]
        _pub = False
        for _ in range(14):
            # nút Publish theo id (không disabled) — chắc nhất
            try:
                _pb = page.locator('#publish-button button:not([disabled]), '
                                   'ytcp-button#publish-button:not([aria-disabled="true"])')
                if await _pb.count() > 0 and await _pb.first.is_visible():
                    await _pb.first.click(timeout=3000)
                    log_fn("  [BÌA] ✓ Bấm Publish")
                    _pub = True
                    break
            except Exception:
                pass
            if await _click_btn(_pub_txt):
                log_fn("  [BÌA] ✓ Bấm Publish (text)")
                _pub = True
                break
            await _dismiss_studio_popups(page, log_fn)
            await page.wait_for_timeout(1000)

        if not _pub:
            try:
                await page.screenshot(path=_dbg_path("debug_banner_publish.png"), timeout=5000)
            except Exception:
                pass
            log_fn("  [BÌA] ⚠ KHÔNG bấm được Publish → ảnh bìa CHƯA lưu (xem debug_banner_publish.png).")
            return False, "", "Không bấm được Publish (ảnh bìa chưa lưu)"

        # Đợi 10s cho YouTube xử lý xong (theo yêu cầu) rồi mới sang nhiệm vụ khác
        log_fn("  [BÌA] Đã Publish — đợi 10s cho YouTube xử lý…")
        await page.wait_for_timeout(10000)
        log_fn(f"  [BÌA] ✅ Đã thay ảnh bìa: {_fname}")
        return True, "", f"Đã thay ảnh bìa ({_fname})"

async def _channel_title(page, cid: str) -> str:
    """Lấy TÊN kênh (để search Google Images) qua og:title của trang kênh."""
    if not cid:
        return ""
    try:
        p2 = await page.context.new_page()
        try:
            await p2.goto(f"https://www.youtube.com/channel/{cid}?hl=en",
                          wait_until="domcontentloaded", timeout=40000)
            await p2.wait_for_timeout(1500)
            t = await p2.evaluate(
                "() => { const m=document.querySelector('meta[property=\"og:title\"]');"
                " return m?m.content:(document.title||''); }")
            t = (t or "").replace(" - YouTube", "").strip()
            return t
        finally:
            try:
                await p2.close()
            except Exception:
                pass
    except Exception:
        return ""


def _is_real_image(b: bytes) -> bool:
    """Đúng là file ảnh (magic number), không phải trang HTML lỗi. >= 15KB."""
    if not b or len(b) < 15000:
        return False
    return (b[:3] == b"\xff\xd8\xff"                       # JPEG
            or b[:8] == b"\x89PNG\r\n\x1a\n"               # PNG
            or b[:6] in (b"GIF87a", b"GIF89a")             # GIF
            or (b[:4] == b"RIFF" and b[8:12] == b"WEBP")   # WEBP
            or b[:2] == b"BM")                             # BMP


def _img_dims(b: bytes) -> tuple:
    """Trả (width, height) của ảnh. Thử PIL trước; nếu không có PIL thì ĐỌC HEADER trực tiếp
    (JPEG/PNG/GIF) để vẫn đo được kích thước. Không đọc được → (0, 0)."""
    try:
        from PIL import Image
        import io as _io
        im = Image.open(_io.BytesIO(b))
        return int(im.size[0]), int(im.size[1])
    except Exception:
        pass
    try:
        # PNG: IHDR ở byte 16..24 (big-endian)
        if b[:8] == b"\x89PNG\r\n\x1a\n" and b[12:16] == b"IHDR":
            w = int.from_bytes(b[16:20], "big"); h = int.from_bytes(b[20:24], "big")
            return w, h
        # GIF: width/height ở byte 6..10 (little-endian)
        if b[:6] in (b"GIF87a", b"GIF89a"):
            w = int.from_bytes(b[6:8], "little"); h = int.from_bytes(b[8:10], "little")
            return w, h
        # JPEG: quét marker SOF để lấy H, W
        if b[:2] == b"\xff\xd8":
            i, n = 2, len(b)
            SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                   0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
            while i + 9 < n:
                if b[i] != 0xFF:
                    i += 1
                    continue
                m = b[i + 1]
                if m in SOF:
                    h = (b[i + 5] << 8) + b[i + 6]
                    w = (b[i + 7] << 8) + b[i + 8]
                    return w, h
                if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                seg = (b[i + 2] << 8) + b[i + 3]
                if seg <= 0:
                    break
                i += 2 + seg
    except Exception:
        pass
    return 0, 0


async def _bing_image_urls(page, query: str) -> list:
    """Lấy URL ảnh GỐC (lớn) từ Bing Images qua thuộc tính murl. Bing nhúng thẳng URL
    ảnh gốc → dễ & ổn định hơn Google. Lọc cỡ Large (~full HD)."""
    import urllib.parse as _up
    q = _up.quote(query)
    url = (f"https://www.bing.com/images/search?q={q}"
           f"&qft=+filterui:imagesize-large&form=IRFLTR")
    ip = None
    try:
        ip = await page.context.new_page()
        try:
            await ip.goto(url, wait_until="domcontentloaded", timeout=40000)
        except Exception:
            pass
        await ip.wait_for_timeout(1800)
        for _ in range(3):
            try:
                await ip.mouse.wheel(0, 2600)
            except Exception:
                pass
            await ip.wait_for_timeout(700)
        try:
            html = await ip.content()
        except Exception:
            html = ""
    finally:
        if ip is not None:
            try:
                await ip.close()
            except Exception:
                pass
    out = []
    # murl nằm trong thuộc tính m="{...murl:...}" — chuẩn hoá entity rồi trích cả 2 dạng.
    _h = (html or "").replace("&quot;", '"').replace("&amp;", "&")
    for u in _re.findall(r'"murl":"(https?://.*?)"', _h):
        low = u.lower().split("?")[0]
        if low.endswith((".jpg", ".jpeg", ".png", ".webp")) and u not in out:
            out.append(u)
    if not out:   # dự phòng: bắt mọi URL ảnh trong mediaurl=/murl chưa chuẩn
        for u in _re.findall(r'mediaurl=([^&"]+)', _h):
            import urllib.parse as _up2
            u = _up2.unquote(u)
            low = u.lower().split("?")[0]
            if low.endswith((".jpg", ".jpeg", ".png", ".webp")) and u not in out:
                out.append(u)
    return out


async def _google_image_urls(page, query: str) -> list:
    """Dự phòng: trích URL ảnh từ Google Images (lọc Large)."""
    import urllib.parse as _up
    q = _up.quote(query)
    url = f"https://www.google.com/search?q={q}&tbm=isch&tbs=isz:l&hl=en&gl=US"
    ip = None
    try:
        ip = await page.context.new_page()
        try:
            await ip.goto(url, wait_until="domcontentloaded", timeout=40000)
        except Exception:
            pass
        await ip.wait_for_timeout(2000)
        for _c in ["Reject all", "Từ chối tất cả", "Accept all", "I agree"]:
            try:
                b = ip.get_by_role("button", name=_re.compile(_c, _re.I))
                if await b.count() > 0 and await b.first.is_visible():
                    await b.first.click(timeout=3000)
                    await ip.wait_for_timeout(1200)
                    break
            except Exception:
                pass
        for _ in range(3):
            try:
                await ip.mouse.wheel(0, 2500)
            except Exception:
                pass
            await ip.wait_for_timeout(700)
        try:
            html = await ip.content()
        except Exception:
            html = ""
    finally:
        if ip is not None:
            try:
                await ip.close()
            except Exception:
                pass
    out = []
    for m in _re.findall(r'https?://[^"\\\s]+?\.(?:jpg|jpeg|png|webp)', html or ""):
        low = m.lower()
        if any(bad in low for bad in ["gstatic.com", "google.com", "googleusercontent",
                                      "ggpht.com", "ytimg.com", "schema.org", "w3.org",
                                      "googleapis.com", "bing.com", "microsoft.com"]):
            continue
        if m not in out:
            out.append(m)
    return out


async def _random_hd_download(page, save_path: str, log_fn=print) -> bool:
    """DỰ PHÒNG: tải 1 ảnh HD NGẪU NHIÊN từ nguồn ổn định (không cần key) khi search
    tên kênh không ra ảnh. Trả True nếu tải được ảnh hợp lệ."""
    import random as _rnd
    _seed = _rnd.randint(1, 9_999_999)
    # nhiều nguồn ảnh ngẫu nhiên HD ~1200px (thử lần lượt cho tới khi được)
    urls = [
        f"https://picsum.photos/seed/{_seed}/1200/1200",
        f"https://picsum.photos/1200/1200?random={_seed}",
        f"https://loremflickr.com/1200/1200?lock={_seed}",
        f"https://picsum.photos/seed/{_seed + 1}/1080/1080",
    ]
    for u in urls:
        try:
            resp = await page.context.request.get(u, timeout=25000)
            if not resp.ok:
                continue
            data = await resp.body()
            if not _is_real_image(data):
                continue
            w, h = _img_dims(data)
            if w and min(w, h) < 400:   # bỏ ảnh nhỏ
                continue
            with open(save_path, "wb") as f:
                f.write(data)
            _d = f"{w}x{h}" if w else "?"
            log_fn(f"  [AVATAR] ✓ Ảnh HD ngẫu nhiên (tên kênh không ra ảnh) {len(data)//1024} KB ({_d}).")
            return True
        except Exception:
            continue
    log_fn("  [AVATAR] ⚠ Cả nguồn ảnh ngẫu nhiên cũng không tải được (mạng?).")
    return False


async def _google_image_download(page, query: str, save_path: str, log_fn=print) -> bool:
    """Tải 1 ảnh LỚN (full HD) liên quan tới `query` về save_path.
    Ưu tiên BING Images (lấy URL ảnh gốc dễ & ổn định), dự phòng Google, cuối cùng dự phòng
    ẢNH HD NGẪU NHIÊN khi tên kênh không ra ảnh nào.
    Có kiểm tra magic-number để không lưu nhầm HTML. Trả True nếu tải được ảnh hợp lệ."""
    import random as _rnd
    if not query:
        return await _random_hd_download(page, save_path, log_fn)
    pool = []
    try:
        pool = await _bing_image_urls(page, query)
        if pool:
            log_fn(f"  [AVATAR] Bing Images: {len(pool)} ảnh ứng viên (Large).")
    except Exception:
        pool = []
    if not pool:
        try:
            pool = await _google_image_urls(page, query)
            if pool:
                log_fn(f"  [AVATAR] Google Images (dự phòng): {len(pool)} ảnh ứng viên.")
        except Exception:
            pool = []
    if not pool:
        log_fn("  [AVATAR] ⚠ Tên kênh không ra ảnh (Bing+Google trống) → dùng ảnh HD ngẫu nhiên.")
        return await _random_hd_download(page, save_path, log_fn)
    _rnd.shuffle(pool)
    # Tải nhiều ứng viên, ĐO kích thước, CHỌN ẢNH TO NHẤT (nét nhất) — bỏ ảnh nhỏ/mờ.
    # Nếu gặp ảnh HD rõ (cạnh lớn ≥ 1280) thì lấy luôn cho nhanh.
    _MIN_SHORT = 400          # loại ảnh quá nhỏ (mờ)
    _HD_LONG = 1280           # đủ nét → lấy ngay
    _best = None              # (data, w, h) ảnh diện tích lớn nhất
    _tried = 0
    for u in pool[:16]:
        if _tried >= 12:
            break
        try:
            resp = await page.context.request.get(u, timeout=25000)
            if not resp.ok:
                continue
            data = await resp.body()
            if not _is_real_image(data):
                continue
            _tried += 1
            w, h = _img_dims(data)
            if w and h and min(w, h) < _MIN_SHORT:
                log_fn(f"  [AVATAR] (bỏ ảnh nhỏ {w}x{h})")
                continue
            if _best is None or (w * h) > (_best[1] * _best[2]):
                _best = (data, w, h)
            # ảnh đủ nét → dùng ngay
            if w and max(w, h) >= _HD_LONG:
                with open(save_path, "wb") as f:
                    f.write(data)
                log_fn(f"  [AVATAR] ✓ Ảnh avatar HD {len(data)//1024} KB ({w}x{h}).")
                return True
        except Exception:
            continue
    if _best is not None:
        with open(save_path, "wb") as f:
            f.write(_best[0])
        _d = f"{_best[1]}x{_best[2]}" if _best[1] else "?"
        log_fn(f"  [AVATAR] ✓ Chọn ảnh to nhất tìm được ({_d}, {len(_best[0])//1024} KB).")
        return True
    log_fn("  [AVATAR] ⚠ Ảnh theo tên kênh không hợp lệ → dùng ảnh HD ngẫu nhiên.")
    return await _random_hd_download(page, save_path, log_fn)


async def do_change_avatar(ws_url: str, email: str = "", data_dir: str = "",
                           log_fn=print) -> tuple[bool, str, str]:
    """Đổi ẢNH ĐẠI DIỆN (avatar) kênh brand: search tên kênh trên Google Images
    (Recent + Large) → tải ngẫu nhiên 1/10 ảnh mới nhất → set vào khối 'Picture'.
    Trả (success, code, message)."""
    import os as _os
    _os.makedirs(data_dir or ".", exist_ok=True)
    _avt = _os.path.join(data_dir or ".", "avatar_src.jpg")

    async with async_playwright() as p:
        log_fn("  [AVATAR] Kết nối browser…")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        try:
            await ctx.add_cookies([
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".youtube.com", "path": "/"},
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".google.com", "path": "/"},
            ])
        except Exception:
            pass
        page = await ctx.new_page()

        # (a) English + (b) vào Studio + chọn kênh brand (thứ 2) — như luồng ảnh bìa
        await _set_youtube_language_english(page, log_fn)
        try:
            await page.goto("https://studio.youtube.com/?hl=en",
                            wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        await _dismiss_studio_popups(page, log_fn)
        cur_cid = await _extract_channel_id(page)
        brand_cid = await _brand_channel_id_via_switcher(page, cur_cid, log_fn)
        if not brand_cid:
            try:
                await page.goto("https://studio.youtube.com/?hl=en",
                                wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2000)
            except Exception:
                pass
            await _dismiss_studio_popups(page, log_fn)
            brand_cid = await _switch_to_second_channel(page, log_fn)
            if brand_cid == "FAIL":
                return False, "", ("Không chuyển được sang kênh thứ 2 (brand) để đổi avatar. "
                                   "Xem debug_select_channel.png")
        await _dismiss_studio_popups(page, log_fn)
        cid = brand_cid or cur_cid or await _extract_channel_id(page)
        for _ in range(4):
            if cid:
                break
            await page.wait_for_timeout(2000)
            cid = await _extract_channel_id(page)
        if not cid:
            _dead = await _channel_dead_reason(page)
            if _dead:
                return False, "KÊNH DIE", f"KÊNH DIE ({_dead})"
            return False, "", "Không lấy được channel ID để đổi avatar"

        # (c) Lấy TÊN kênh + tải ảnh từ Google Images
        cname = await _channel_title(page, cid)
        log_fn(f"  [AVATAR] Tên kênh để search: {cname or '(trống)'}")
        if not cname:
            return False, "", "Không lấy được tên kênh để search Google Images"
        if not await _google_image_download(page, cname, _avt, log_fn):
            return False, "", "Không tải được ảnh avatar từ Google Images (xem debug_avatar_gimg.png)"

        # (d) Mở trang tùy chỉnh (cùng trang với ảnh bìa: có khối 'Picture')
        log_fn("  [AVATAR] Mở trang tùy chỉnh để đổi ảnh đại diện…")
        try:
            await page.goto(f"https://studio.youtube.com/channel/{cid}/editing/images?hl=en",
                            wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        await _dismiss_studio_popups(page, log_fn)
        _ready = False
        for _i in range(40):
            try:
                if await page.locator('input[type="file"]').count() > 0:
                    _ready = True
                if not _ready:
                    for _t in ["Picture", "Profile picture", "Ảnh đại diện", "Banner image"]:
                        if await page.get_by_text(_re.compile(_t, _re.I)).count() > 0:
                            _ready = True
                            break
            except Exception:
                pass
            if _ready:
                break
            await page.wait_for_timeout(1000)
            if _i in (10, 20, 30):
                await _dismiss_studio_popups(page, log_fn)
        _u_now = page.url or ""
        if cid not in _u_now or "/editing/" not in _u_now:
            try:
                await page.screenshot(path=_dbg_path("debug_avatar_page.png"), timeout=5000)
            except Exception:
                pass
            return False, "", (f"Không mở được trang tùy chỉnh kênh {cid} để đổi avatar "
                               "(xem debug_avatar_page.png)")
        await page.wait_for_timeout(1500)

        # (e) ĐƯA ẢNH vào khối 'Picture' (KHÔNG phải Banner). Picture là khối THỨ 2 trên trang.
        _PIC_TXT = ["Picture", "Profile picture", "Ảnh đại diện", "รูปโปรไฟล์", "รูปภาพ"]
        _BTN_TXT = ["Change", "Upload", "Thay đổi", "Tải lên", "เปลี่ยน", "変更", "변경", "更改"]
        _did = False

        async def _try_section(sec) -> bool:
            try:
                finp = sec.locator('input[type="file"]')
                if await finp.count() > 0:
                    await finp.first.set_input_files(_avt)
                    return True
            except Exception:
                pass
            for _t in _BTN_TXT:
                try:
                    b = sec.locator(f'button:has-text("{_t}"), ytcp-button:has-text("{_t}"), '
                                    f'[role="button"]:has-text("{_t}")')
                    if await b.count() > 0 and await b.first.is_visible():
                        async with page.expect_file_chooser(timeout=8000) as _fc:
                            await b.first.click(timeout=3000)
                        chooser = await _fc.value
                        await chooser.set_files(_avt)
                        return True
                except Exception:
                    pass
            return False

        # (e1) khối chứa tiêu đề 'Picture'
        for _sec_txt in _PIC_TXT:
            if _did:
                break
            for _sel in (f'ytcp-form-file-picker:has-text("{_sec_txt}")',
                         f'div:has(> h2:has-text("{_sec_txt}"))',
                         f'div:has(> h3:has-text("{_sec_txt}"))',
                         '[id*="avatar" i]', '[id*="picture" i]'):
                try:
                    sec = page.locator(_sel)
                    if await sec.count() > 0 and await _try_section(sec.first):
                        _did = True
                        log_fn(f"  [AVATAR] ✓ Đưa ảnh vào khối '{_sec_txt}'")
                        break
                except Exception:
                    pass
        # (e2) dự phòng: picker THỨ 2 (Banner đứng trên, Picture đứng dưới)
        if not _did:
            try:
                pickers = page.locator('ytcp-form-file-picker')
                if await pickers.count() >= 2 and await _try_section(pickers.nth(1)):
                    _did = True
                    log_fn("  [AVATAR] ✓ Đưa ảnh vào khối Picture (picker thứ 2)")
            except Exception:
                pass
        # (e3) dự phòng cuối: input file THỨ 2 của trang
        if not _did:
            try:
                finp = page.locator('input[type="file"]')
                if await finp.count() >= 2:
                    await finp.nth(1).set_input_files(_avt)
                    _did = True
                    log_fn("  [AVATAR] ✓ Đưa ảnh vào input file thứ 2 (Picture)")
            except Exception:
                pass
        if not _did:
            try:
                await page.screenshot(path=_dbg_path("debug_avatar_page.png"), timeout=5000)
            except Exception:
                pass
            return False, "", "Không đưa được ảnh vào khối 'Picture' (xem debug_avatar_page.png)"

        # (f) Hộp crop → Done (theo cấu trúc, không phụ thuộc ngôn ngữ)
        async def _visible_click(loc, timeout_ms=3000) -> bool:
            try:
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click(timeout=timeout_ms)
                    return True
            except Exception:
                pass
            return False

        async def _click_crop_done() -> bool:
            dlg = page.locator('tp-yt-paper-dialog[opened], ytcp-dialog, '
                               'ytcp-uploads-dialog, div[role="dialog"]')
            if await dlg.count() == 0:
                return False
            d = dlg.last
            for sel in ['#done-button', '#confirm-button', '#save-button',
                        'ytcp-button[type="primary"]', 'ytcp-button.primary',
                        '[id*="done"]', '[id*="confirm"]']:
                if await _visible_click(d.locator(sel)):
                    return True
            try:
                btns = d.locator('ytcp-button, tp-yt-paper-button')
                keep = []
                n = await btns.count()
                for i in range(n):
                    b = btns.nth(i)
                    try:
                        if not await b.is_visible():
                            continue
                        _t = ((await b.get_attribute("aria-label") or "") + " " +
                              (await b.inner_text() or "")).lower()
                        if any(c in _t for c in ["cancel", "hủy", "huỷ", "close", "đóng"]):
                            continue
                        keep.append(i)
                    except Exception:
                        pass
                if keep and await _visible_click(btns.nth(keep[-1])):
                    return True
            except Exception:
                pass
            for t in ["Done", "Xong", "เสร็จ", "완료", "完成", "OK"]:
                try:
                    b = page.locator(f'ytcp-button:has-text("{t}"), button:has-text("{t}"), '
                                     f'[role="button"]:has-text("{t}")')
                    if await b.count() > 0 and await b.first.is_visible():
                        await b.first.click(timeout=3000)
                        return True
                except Exception:
                    pass
            return False

        for _ in range(15):
            await page.wait_for_timeout(1000)
            if await _click_crop_done():
                log_fn("  [AVATAR] ✓ Bấm Done (crop)")
                break
        await page.wait_for_timeout(1500)
        await _dismiss_studio_popups(page, log_fn)

        # (g) CHỜ Publish bật rồi bấm
        _pub_txt = ["Publish", "Xuất bản", "เผยแพร่", "게시", "發布", "发布", "公開"]
        _pub = False
        for _ in range(14):
            try:
                _pb = page.locator('#publish-button button:not([disabled]), '
                                   'ytcp-button#publish-button:not([aria-disabled="true"])')
                if await _pb.count() > 0 and await _pb.first.is_visible():
                    await _pb.first.click(timeout=3000)
                    _pub = True
                    break
            except Exception:
                pass
            for t in _pub_txt:
                try:
                    b = page.locator(f'ytcp-button:has-text("{t}"), button:has-text("{t}"), '
                                     f'[role="button"]:has-text("{t}")')
                    if await b.count() > 0 and await b.first.is_visible():
                        await b.first.click(timeout=3000)
                        _pub = True
                        break
                except Exception:
                    pass
            if _pub:
                break
            await _dismiss_studio_popups(page, log_fn)
            await page.wait_for_timeout(1000)
        if not _pub:
            try:
                await page.screenshot(path=_dbg_path("debug_avatar_publish.png"), timeout=5000)
            except Exception:
                pass
            return False, "", "Không bấm được Publish (avatar chưa lưu)"

        log_fn("  [AVATAR] Đã Publish — đợi 10s cho YouTube xử lý…")
        await page.wait_for_timeout(10000)
        log_fn("  [AVATAR] ✅ Đã đổi ảnh đại diện.")
        return True, "", "Đã đổi avatar (Google Images)"

async def _shot_region(page, path: str, texts, min_w=170, min_h=100) -> bool:
    """Chụp 1 VÙNG: phần tử hiển thị NHỎ NHẤT chứa hết `texts` (không phân biệt hoa/thường)
    và đủ lớn (>= min_w x min_h). Lưu ra path. Trả True nếu chụp được."""
    try:
        handle = await page.evaluate_handle(r"""(args) => {
            const [texts, minW, minH] = args;
            let best = null, ba = 1e18;
            for (const e of document.querySelectorAll('*')) {
                if (e.offsetParent === null) continue;
                const r = e.getBoundingClientRect();
                if (r.width < minW || r.height < minH) continue;
                const t = (e.innerText || '').toLowerCase();
                let ok = true;
                for (const x of texts) { if (t.indexOf(String(x).toLowerCase()) < 0) { ok = false; break; } }
                if (!ok) continue;
                const a = r.width * r.height;
                if (a < ba) { ba = a; best = e; }
            }
            return best;
        }""", [texts, min_w, min_h])
        el = handle.as_element() if handle else None
        if not el:
            return False
        try:
            await el.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        await el.screenshot(path=path)
        return True
    except Exception:
        return False


async def _capture_channel_shots(page, cid: str, data_dir: str, log_fn=print) -> tuple[list, list]:
    """Chụp các ảnh THÔNG TIN KÊNH (kênh thứ 2/brand) → lưu 1.png, 2.png,… vào data_dir.
    Trả (danh sách ảnh OK, danh sách ảnh lỗi). Mỗi ảnh là 1 VÙNG cụ thể."""
    import os as _os
    _ok, _err = [], []
    _n = [0]

    def _path():
        _n[0] += 1
        return _os.path.join(data_dir, f"{_n[0]}.png"), _n[0]

    # Về trang KÊNH (giống 'View your channel'); PREF đã ép tiếng Anh nên hộp là 'More info'.
    try:
        await page.goto(f"https://www.youtube.com/channel/{cid}?hl=en",
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3500)
    except Exception:
        pass
    # bỏ qua consent cookie nếu có
    for _c in ["Reject all", "Accept all", "I agree", "Từ chối tất cả", "Chấp nhận tất cả"]:
        try:
            b = page.get_by_role("button", name=_re.compile(_c, _re.I))
            if await b.count() > 0 and await b.first.is_visible():
                await b.first.click(timeout=3000)
                await page.wait_for_timeout(1200)
                break
        except Exception:
            pass

    # ── ẢNH 1: bấm '...more' → hộp 'More info' → chụp hộp đó ──
    _more = False
    for _mt in ["…more", "...more", "More about this channel", "more"]:
        if _more:
            break
        try:
            b = page.get_by_text(_re.compile(_re.escape(_mt), _re.I))
            for i in range(min(await b.count(), 6)):
                el = b.nth(i)
                if await el.is_visible():
                    await el.click(timeout=4000)
                    _more = True
                    break
        except Exception:
            pass
    if not _more:
        try:
            b = page.get_by_role("button", name=_re.compile("more about this channel", _re.I))
            if await b.count() > 0 and await b.first.is_visible():
                await b.first.click(timeout=4000)
                _more = True
        except Exception:
            pass
    # chờ hộp 'More info' hiện
    _dlg_ok = False
    for _ in range(12):
        await page.wait_for_timeout(1000)
        try:
            if await page.get_by_text(_re.compile(r"More info|Joined", _re.I)).count() > 0:
                _dlg_ok = True
                break
        except Exception:
            pass
    p1, i1 = _path()
    # Chụp NGUYÊN KHUNG NHÌN (viewport) — hộp 'More info' ở giữa + nền trang, đẹp & dễ nhìn.
    try:
        await page.screenshot(path=p1)   # mặc định = viewport (không full_page)
        if _dlg_ok:
            _ok.append(f"{i1}")
            log_fn(f"  [DATA] ✓ Chụp ảnh {i1} (More info, cả khung nhìn).")
        else:
            # vẫn chụp nhưng cảnh báo có thể chưa mở được hộp
            _ok.append(f"{i1}")
            log_fn(f"  [DATA] ⚠ Chụp ảnh {i1} nhưng CHƯA chắc mở được hộp 'More info'.")
    except Exception as _e1:
        _err.append(f"{i1}(More info)")
        log_fn(f"  [DATA] ⚠ Không chụp được ảnh {i1}: {_e1}")
    # đóng hộp More info
    try:
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(800)
    except Exception:
        pass

    # ── ẢNH 2: Studio → Settings → Channel → tab 'Feature eligibility' → chụp khung nhìn ──
    async def _click_txt(patterns, tries=1, exact=False) -> bool:
        for _ in range(tries):
            for pt in patterns:
                try:
                    rx = _re.compile((rf"^\s*{_re.escape(pt)}\s*$" if exact else _re.escape(pt)), _re.I)
                    b = page.get_by_text(rx)
                    for i in range(min(await b.count(), 8)):
                        el = b.nth(i)
                        if await el.is_visible():
                            await el.click(timeout=4000)
                            return True
                except Exception:
                    pass
            await page.wait_for_timeout(1000)
        return False

    try:
        await page.goto(f"https://studio.youtube.com/channel/{cid}?hl=en",
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(3500)
    except Exception:
        pass
    await _dismiss_studio_popups(page, log_fn)
    # mở Settings (góc trái dưới)
    _sopen = False
    for _sel in ('#settings-item', 'a[href$="/settings"]',
                 'ytcp-button:has-text("Settings")',
                 'tp-yt-paper-icon-item:has-text("Settings")'):
        try:
            b = page.locator(_sel)
            if await b.count() > 0 and await b.first.is_visible():
                await b.first.click(timeout=4000)
                _sopen = True
                break
        except Exception:
            pass
    if not _sopen:
        _sopen = await _click_txt(["Settings", "Cài đặt"], tries=2, exact=True)
    # chờ hộp Settings mở
    for _ in range(10):
        await page.wait_for_timeout(1000)
        try:
            if await page.get_by_text(_re.compile(r"Upload defaults|Feature eligibility", _re.I)).count() > 0:
                break
        except Exception:
            pass
    await _click_txt(["Channel"], tries=2, exact=True)     # menu trái 'Channel'
    await page.wait_for_timeout(1500)
    await _click_txt(["Feature eligibility"], tries=3)      # tab 'Feature eligibility'
    for _ in range(8):                                     # chờ nội dung tab
        await page.wait_for_timeout(1000)
        try:
            if await page.get_by_text(_re.compile(r"Advanced features|Standard features", _re.I)).count() > 0:
                break
        except Exception:
            pass
    p2, i2 = _path()
    try:
        await page.screenshot(path=p2)
        _ok.append(f"{i2}")
        log_fn(f"  [DATA] ✓ Chụp ảnh {i2} (Feature eligibility).")
    except Exception as _e2:
        _err.append(f"{i2}(Feature eligibility)")
        log_fn(f"  [DATA] ⚠ Không chụp được ảnh {i2}: {_e2}")
    try:
        await _click_txt(["Close", "Đóng"], tries=1, exact=True)
        await page.wait_for_timeout(600)
    except Exception:
        pass

    # ── ẢNH 3: Studio → Analytics (Overview) → chụp khung nhìn ──
    try:
        await page.goto(
            f"https://studio.youtube.com/channel/{cid}/analytics/tab-overview/period-default?hl=en",
            wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(4000)
    except Exception:
        pass
    await _dismiss_studio_popups(page, log_fn)
    # nếu chưa thấy nội dung Analytics → bấm mục 'Analytics' ở menu trái
    _an_ok = False
    for _ in range(10):
        try:
            if await page.get_by_text(
                    _re.compile(r"Channel analytics|views in the last|Realtime", _re.I)).count() > 0:
                _an_ok = True
                break
        except Exception:
            pass
        await page.wait_for_timeout(1000)
    if not _an_ok:
        await _click_txt(["Analytics"], tries=2, exact=True)
        for _ in range(8):
            try:
                if await page.get_by_text(
                        _re.compile(r"Channel analytics|views in the last|Realtime", _re.I)).count() > 0:
                    break
            except Exception:
                pass
            await page.wait_for_timeout(1000)
    p3, i3 = _path()
    try:
        await page.screenshot(path=p3)
        _ok.append(f"{i3}")
        log_fn(f"  [DATA] ✓ Chụp ảnh {i3} (Analytics).")
    except Exception as _e3:
        _err.append(f"{i3}(Analytics)")
        log_fn(f"  [DATA] ⚠ Không chụp được ảnh {i3}: {_e3}")

    # ── ẢNH 4: Studio → Dashboard → chụp khung nhìn ──
    try:
        await page.goto(f"https://studio.youtube.com/channel/{cid}?hl=en",
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(4000)
    except Exception:
        pass
    await _dismiss_studio_popups(page, log_fn)
    _db_ok = False
    for _ in range(10):
        try:
            if await page.get_by_text(
                    _re.compile(r"Channel dashboard|Published videos|Recent subscribers", _re.I)).count() > 0:
                _db_ok = True
                break
        except Exception:
            pass
        await page.wait_for_timeout(1000)
    if not _db_ok:
        await _click_txt(["Dashboard"], tries=2, exact=True)
        for _ in range(8):
            try:
                if await page.get_by_text(
                        _re.compile(r"Channel dashboard|Published videos", _re.I)).count() > 0:
                    break
            except Exception:
                pass
            await page.wait_for_timeout(1000)
    p4, i4 = _path()
    try:
        await page.screenshot(path=p4)
        _ok.append(f"{i4}")
        log_fn(f"  [DATA] ✓ Chụp ảnh {i4} (Dashboard).")
    except Exception as _e4:
        _err.append(f"{i4}(Dashboard)")
        log_fn(f"  [DATA] ⚠ Không chụp được ảnh {i4}: {_e4}")

    return _ok, _err


async def do_taodata_images(ws_url: str, email: str = "", banner_dir: str = "",
                            data_dir: str = "", log_fn=print) -> tuple[bool, str, str]:
    """TẠO DATA (bìa + avatar) trong CÙNG 1 PHIÊN Studio:
      - Đổi ảnh bìa (ảnh ngẫu nhiên trong banner_dir).
      - Đổi avatar: search TÊN KÊNH THỨ 2 (brand) trên Google Images (Recent+Large),
        chọn ngẫu nhiên 1/10 ảnh mới nhất, tải về data_dir, set vào khối 'Picture'.
      - Publish 1 lần cho cả 2 thay đổi.
    Lỗi 1 bước vẫn làm bước còn lại. Trả (success, code, detail)."""
    import os as _os
    _os.makedirs(data_dir or ".", exist_ok=True)
    _avt = _os.path.join(data_dir or ".", "avatar_src.jpg")
    banner = _pick_random_banner(banner_dir)
    _bfname = _os.path.basename(banner) if banner else ""
    _ok, _err = [], []

    async with async_playwright() as p:
        log_fn("  [DATA] Kết nối browser…")
        browser = await p.chromium.connect_over_cdp(ws_url)
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        try:
            await ctx.add_cookies([
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".youtube.com", "path": "/"},
                {"name": "PREF", "value": "hl=en&gl=US", "domain": ".google.com", "path": "/"},
            ])
        except Exception:
            pass
        page = await ctx.new_page()

        # (a) English + (b) Studio + chọn kênh brand (kênh thứ 2)
        await _set_youtube_language_english(page, log_fn)
        try:
            await page.goto("https://studio.youtube.com/?hl=en",
                            wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        await _dismiss_studio_popups(page, log_fn)
        cur_cid = await _extract_channel_id(page)
        brand_cid = await _brand_channel_id_via_switcher(page, cur_cid, log_fn)
        if not brand_cid:
            try:
                await page.goto("https://studio.youtube.com/?hl=en",
                                wait_until="domcontentloaded", timeout=45000)
                await page.wait_for_timeout(2000)
            except Exception:
                pass
            await _dismiss_studio_popups(page, log_fn)
            brand_cid = await _switch_to_second_channel(page, log_fn)
            if brand_cid == "FAIL":
                return False, "", ("Không chuyển được sang kênh thứ 2 (brand) — dừng để tránh "
                                   "đổi nhầm kênh 1. Xem debug_select_channel.png")
        await _dismiss_studio_popups(page, log_fn)
        cid = brand_cid or cur_cid or await _extract_channel_id(page)
        for _ in range(4):
            if cid:
                break
            await page.wait_for_timeout(2000)
            cid = await _extract_channel_id(page)
        if not cid:
            _dead = await _channel_dead_reason(page)
            if _dead:
                return False, "KÊNH DIE", f"KÊNH DIE ({_dead})"
            return False, "", "Không lấy được channel ID (chưa có kênh?)"
        log_fn(f"  [DATA] Kênh brand (thứ 2): {cid}")

        # (c) TÊN kênh THỨ 2 → tải avatar từ Google Images (làm TRƯỚC, để lát set cùng lúc)
        cname = await _channel_title(page, cid)
        log_fn(f"  [DATA] Tên kênh thứ 2 để search: {cname or '(trống)'}")
        _avt_ok = False
        if cname:
            _avt_ok = await _google_image_download(page, cname, _avt, log_fn)
            if not _avt_ok:
                _err.append("avatar(không tải được ảnh Google)")
        else:
            _err.append("avatar(không lấy được tên kênh)")

        # (d) Mở trang tùy chỉnh (có cả khối Banner + Picture)
        log_fn("  [DATA] Mở trang tùy chỉnh (Customization)…")
        try:
            await page.goto(f"https://studio.youtube.com/channel/{cid}/editing/images?hl=en",
                            wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass
        await _dismiss_studio_popups(page, log_fn)
        _ready = False
        for _i in range(40):
            try:
                if await page.locator('input[type="file"]').count() > 0:
                    _ready = True
                if not _ready:
                    for _t in ["Banner image", "Picture", "Ảnh bìa", "Ảnh đại diện"]:
                        if await page.get_by_text(_re.compile(_t, _re.I)).count() > 0:
                            _ready = True
                            break
            except Exception:
                pass
            if _ready:
                break
            await page.wait_for_timeout(1000)
            if _i in (10, 20, 30):
                await _dismiss_studio_popups(page, log_fn)
        _u_now = page.url or ""
        if cid not in _u_now or "/editing/" not in _u_now:
            try:
                await page.screenshot(path=_dbg_path("debug_data_page.png"), timeout=5000)
            except Exception:
                pass
            return False, "", (f"Không mở được trang tùy chỉnh kênh {cid} (xem debug_data_page.png)")
        await page.wait_for_timeout(1500)

        # ── Helper set file + crop Done + publish ──────────────────────────
        async def _try_section(sec, filepath) -> bool:
            try:
                finp = sec.locator('input[type="file"]')
                if await finp.count() > 0:
                    await finp.first.set_input_files(filepath)
                    return True
            except Exception:
                pass
            for _t in ["Upload", "Change", "Tải lên", "Thay đổi", "อัปโหลด", "เปลี่ยน",
                       "変更", "変更", "변경", "更改"]:
                try:
                    b = sec.locator(f'button:has-text("{_t}"), ytcp-button:has-text("{_t}"), '
                                    f'[role="button"]:has-text("{_t}")')
                    if await b.count() > 0 and await b.first.is_visible():
                        async with page.expect_file_chooser(timeout=8000) as _fc:
                            await b.first.click(timeout=3000)
                        chooser = await _fc.value
                        await chooser.set_files(filepath)
                        return True
                except Exception:
                    pass
            return False

        async def _visible_click(loc, timeout_ms=3000) -> bool:
            try:
                if await loc.count() > 0 and await loc.first.is_visible():
                    await loc.first.click(timeout=timeout_ms)
                    return True
            except Exception:
                pass
            return False

        async def _click_crop_done() -> bool:
            dlg = page.locator('tp-yt-paper-dialog[opened], ytcp-dialog, '
                               'ytcp-uploads-dialog, div[role="dialog"]')
            if await dlg.count() == 0:
                return False
            d = dlg.last
            for sel in ['#done-button', '#confirm-button', '#save-button',
                        'ytcp-button[type="primary"]', 'ytcp-button.primary',
                        '[id*="done"]', '[id*="confirm"]']:
                if await _visible_click(d.locator(sel)):
                    return True
            try:
                btns = d.locator('ytcp-button, tp-yt-paper-button')
                keep = []
                n = await btns.count()
                for i in range(n):
                    b = btns.nth(i)
                    try:
                        if not await b.is_visible():
                            continue
                        _t = ((await b.get_attribute("aria-label") or "") + " " +
                              (await b.inner_text() or "")).lower()
                        if any(c in _t for c in ["cancel", "hủy", "huỷ", "close", "đóng"]):
                            continue
                        keep.append(i)
                    except Exception:
                        pass
                if keep and await _visible_click(btns.nth(keep[-1])):
                    return True
            except Exception:
                pass
            for t in ["Done", "Xong", "เสร็จ", "완료", "完成", "OK"]:
                try:
                    b = page.locator(f'ytcp-button:has-text("{t}"), button:has-text("{t}"), '
                                     f'[role="button"]:has-text("{t}")')
                    if await b.count() > 0 and await b.first.is_visible():
                        await b.first.click(timeout=3000)
                        return True
                except Exception:
                    pass
            return False

        async def _do_crop():
            for _ in range(15):
                await page.wait_for_timeout(1000)
                if await _click_crop_done():
                    return True
            return False

        # (e) ĐỔI ẢNH BÌA (khối Banner = khối ĐẦU / picker thứ 1)
        if not banner:
            _err.append("bìa(không có ảnh trong anh_bia)")
        else:
            _bdone = False
            for _sec_txt in ["Banner image", "Ảnh bìa", "ภาพแบนเนอร์"]:
                if _bdone:
                    break
                for _sel in (f'ytcp-form-file-picker:has-text("{_sec_txt}")',
                             f'div:has(> h2:has-text("{_sec_txt}"))',
                             f'div:has(> h3:has-text("{_sec_txt}"))', '[id*="banner" i]'):
                    try:
                        sec = page.locator(_sel)
                        if await sec.count() > 0 and await _try_section(sec.first, banner):
                            _bdone = True
                            break
                    except Exception:
                        pass
            if not _bdone:
                try:
                    pickers = page.locator('ytcp-form-file-picker')
                    if await pickers.count() >= 1 and await _try_section(pickers.first, banner):
                        _bdone = True
                except Exception:
                    pass
            if not _bdone:
                try:
                    finp = page.locator('input[type="file"]')
                    if await finp.count() > 0:
                        await finp.first.set_input_files(banner)
                        _bdone = True
                except Exception:
                    pass
            if _bdone:
                await _do_crop()
                await page.wait_for_timeout(1200)
                await _dismiss_studio_popups(page, log_fn)
                _ok.append("bìa")
                log_fn(f"  [DATA] ✓ Đã đưa ảnh bìa: {_bfname}")
            else:
                _err.append("bìa(không đưa được ảnh vào khối Banner)")
                log_fn("  [DATA] ⚠ Không đưa được ảnh bìa.")

        # (f) ĐỔI AVATAR (khối Picture = khối THỨ 2 / picker thứ 2) — nếu đã tải được ảnh
        if _avt_ok:
            _vdone = False
            for _sec_txt in ["Picture", "Profile picture", "Ảnh đại diện", "รูปโปรไฟล์"]:
                if _vdone:
                    break
                for _sel in (f'ytcp-form-file-picker:has-text("{_sec_txt}")',
                             f'div:has(> h2:has-text("{_sec_txt}"))',
                             f'div:has(> h3:has-text("{_sec_txt}"))',
                             '[id*="avatar" i]', '[id*="picture" i]'):
                    try:
                        sec = page.locator(_sel)
                        if await sec.count() > 0 and await _try_section(sec.first, _avt):
                            _vdone = True
                            break
                    except Exception:
                        pass
            if not _vdone:
                try:
                    pickers = page.locator('ytcp-form-file-picker')
                    if await pickers.count() >= 2 and await _try_section(pickers.nth(1), _avt):
                        _vdone = True
                except Exception:
                    pass
            if not _vdone:
                try:
                    finp = page.locator('input[type="file"]')
                    if await finp.count() >= 2:
                        await finp.nth(1).set_input_files(_avt)
                        _vdone = True
                except Exception:
                    pass
            if _vdone:
                await _do_crop()
                await page.wait_for_timeout(1200)
                await _dismiss_studio_popups(page, log_fn)
                _ok.append("avatar")
                log_fn("  [DATA] ✓ Đã đưa ảnh avatar vào khối Picture")
            else:
                _err.append("avatar(không đưa được ảnh vào khối Picture)")
                log_fn("  [DATA] ⚠ Không đưa được ảnh avatar.")

        # (g) PUBLISH 1 LẦN cho cả 2 thay đổi (nếu có ít nhất 1 ảnh đã set)
        if "bìa" in _ok or "avatar" in _ok:
            _pub = False
            for _ in range(16):
                try:
                    _pb = page.locator('#publish-button button:not([disabled]), '
                                       'ytcp-button#publish-button:not([aria-disabled="true"])')
                    if await _pb.count() > 0 and await _pb.first.is_visible():
                        await _pb.first.click(timeout=3000)
                        _pub = True
                        break
                except Exception:
                    pass
                for t in ["Publish", "Xuất bản", "เผยแพร่", "게시", "發布", "发布", "公開"]:
                    try:
                        b = page.locator(f'ytcp-button:has-text("{t}"), button:has-text("{t}"), '
                                         f'[role="button"]:has-text("{t}")')
                        if await b.count() > 0 and await b.first.is_visible():
                            await b.first.click(timeout=3000)
                            _pub = True
                            break
                    except Exception:
                        pass
                if _pub:
                    break
                await _dismiss_studio_popups(page, log_fn)
                await page.wait_for_timeout(1000)
            if not _pub:
                try:
                    await page.screenshot(path=_dbg_path("debug_data_publish.png"), timeout=5000)
                except Exception:
                    pass
                # KHÔNG return sớm — vẫn chụp ảnh tiếp; đánh dấu 2 ảnh bìa/avatar là chưa lưu.
                _err.append("publish(không bấm được)")
                if "bìa" in _ok:
                    _ok.remove("bìa"); _err.append("bìa(chưa publish)")
                if "avatar" in _ok:
                    _ok.remove("avatar"); _err.append("avatar(chưa publish)")
                log_fn("  [DATA] ⚠ Không bấm được Publish (bìa/avatar chưa lưu).")
            else:
                log_fn("  [DATA] ✓ Publish — đợi 10s cho YouTube xử lý…")
                await page.wait_for_timeout(10000)

        # (h) CHỤP ẢNH THÔNG TIN KÊNH → lưu 1.png, 2.png,… vào data_dir (chạy dù bìa/avatar lỗi)
        try:
            _sok, _serr = await _capture_channel_shots(page, cid, data_dir, log_fn)
            if _sok:
                _ok.append("ảnh:" + ",".join(_sok))
            if _serr:
                _err.append("ảnh:" + ",".join(_serr))
        except Exception as _se:
            _err.append(f"chụp({_se})")
            log_fn(f"  [DATA] ⚠ Lỗi bước chụp ảnh: {_se}")

        _detail = (("OK: " + " ".join(_ok) if _ok else "")
                   + (("  |  LỖI: " + "; ".join(_err)) if _err else "")).strip()
        _success = (len(_err) == 0 and len(_ok) > 0)
        log_fn(f"  [DATA] ✅ Tạo Data xong — {_detail}")
        return _success, "", _detail or "Không làm được gì"

# (end of module)
