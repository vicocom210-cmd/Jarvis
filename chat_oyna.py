"""
Chat oynasi — brauzer emas, alohida haqiqiy dastur oynasi.
Windows'ning o'z WebView2 (Microsoft Edge dvigateli) ichida ishlaydi: manzil satri, globus
belgisi, brauzer menyulari yo'q. Internet shart emas — sahifa shu kompyuterdagi Jarvis'dan keladi.

Jarvis o'zi ishga tushiradi (alohida jarayon sifatida):
    Jarvis.exe --chat URL        yoki        python chat_oyna.py URL
Kerak: pip install pywebview
"""
import sys

STANDART_URL = "http://127.0.0.1:8770/chat"


def och(url=STANDART_URL):
    import webview
    webview.create_window("Jarvis", url, width=1150, height=780, min_size=(760, 520),
                          background_color="#070B16", text_select=True)
    webview.start()


if __name__ == "__main__":
    och(sys.argv[1] if len(sys.argv) > 1 else STANDART_URL)
