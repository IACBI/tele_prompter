# TelePrompter

> 🇹🇷 [Türkçe açıklama aşağıda](#türkçe)

---

A professional, open-source teleprompter built with Python and PyQt5. Transparent overlay display window with a fully-featured control panel — no external files or dependencies beyond PyQt5.

## Features

| Category | Details |
|---|---|
| **Display** | Transparent overlay, adjustable opacity, always-on-top, drag to reposition, resize via bottom-right grip |
| **Scroll** | Frame-rate-independent (real Δt via QElapsedTimer), smooth at any refresh rate |
| **Word Highlight** | Current word glows amber as it passes through the focus zone |
| **Text Alignment** | Left / Center / Right |
| **Focus Zone** | Top (25%) / Center (50%) / Bottom (75%) reading position |
| **Themes** | Dark · Light · High Contrast · Solarized · Cinema Blue |
| **Font** | Full system font picker + size + line spacing |
| **Mirror Mode** | Horizontal flip for physical beam-splitter glass |
| **Cue Markers** | `[PAUSE]` tag auto-pauses scroll at marked points |
| **Presenter Notes** | `[[note text]]` shows private notes in a side window |
| **WPM Tracker** | Live words-per-minute estimate with colour coding |
| **Auto-Speed** | Mic voice detection — scroll pauses during silence |
| **Touch Controls** | Large overlay buttons for tablet / touchscreen use |
| **Global Hotkeys** | Space / R work system-wide (even when window is unfocused) |
| **Countdown Timer** | 0–10 sec countdown before playback begins |
| **Script Slots** | Save, load and delete named scripts |
| **Auto-Save** | Last script restored automatically on next launch |
| **Undo / Redo** | Full undo/redo stack (buttons + Ctrl+Z / Ctrl+Y) |
| **PDF Export** | Print-ready PDF export of your script |
| **File Loading** | `.txt` in any encoding (UTF-8, Latin-1, Windows-1252 …) + `.pdf` text extraction |

## Requirements

```bash
pip install PyQt5
```

**Optional extras:**

```bash
pip install keyboard          # Global hotkeys (Linux may need sudo)
pip install sounddevice numpy # Mic auto-speed
pip install PyMuPDF           # PDF text import
```

## Quick Start

```bash
python teleprompter.py
```

Two windows open side-by-side automatically:
- **Control Panel** — left side, script editor + all settings
- **Prompter Display** — right side, transparent overlay (drag to reposition, resize from bottom-right corner grip)

## Keyboard Shortcuts

| Key | Action |
|---|---|
| `Space` / `Enter` | Play / Pause |
| `↑` / `↓` | Increase / decrease speed |
| `←` / `→` | Skip backward / forward |
| `R` / `Esc` | Reset to beginning |
| Mouse wheel | Adjust speed (on prompter window) |

## Script Tags

```
[PAUSE]         — scroll auto-pauses at this line
[[your note]]   — shown only in the Presenter Notes window
```

## Author

𝓐.𝓒.𝓑

## License

MIT

---

<a name="türkçe"></a>

# Türkçe

Python ve PyQt5 ile geliştirilmiş profesyonel, açık kaynaklı bir teleprompter. PyQt5 dışında harici dosya veya bağımlılık gerektirmez.

## Özellikler

| Kategori | Detay |
|---|---|
| **Ekran** | Şeffaf bindirme, ayarlanabilir opaklık, her zaman üstte, sürükleyerek konumlandırma, sağ alt köşe tutamacıyla yeniden boyutlandırma |
| **Kaydırma** | Kare hızından bağımsız (QElapsedTimer ile gerçek Δt), her yenileme hızında akıcı |
| **Kelime Vurgusu** | Odak bölgesine gelen kelime amber renginde parlar |
| **Metin Hizalama** | Sola / Ortaya / Sağa |
| **Odak Bölgesi** | Üst (%25) / Orta (%50) / Alt (%75) okuma pozisyonu |
| **Temalar** | Dark · Light · High Contrast · Solarized · Cinema Blue |
| **Font** | Tam sistem font seçici + boyut + satır aralığı |
| **Ayna Modu** | Fiziksel beam-splitter cam için yatay çevirme |
| **İşaret Etiketleri** | `[PAUSE]` etiketi işaretlenen noktada kaydırmayı durdurur |
| **Sunucu Notları** | `[[not metni]]` notları özel bir yan pencerede gösterir |
| **DPD Takibi** | Renk kodlu canlı dakikada kelime tahmini |
| **Otomatik Hız** | Mikrofon ses algılama — sessizlikte kaydırma durur |
| **Dokunmatik Kontroller** | Tablet/dokunmatik ekran için büyük bindirme butonları |
| **Global Kısayollar** | Space / R sistem genelinde çalışır (pencere odakta olmasa bile) |
| **Geri Sayım** | Oynatma başlamadan önce 0–10 saniyelik geri sayım |
| **Script Yuvaları** | Adlandırılmış scriptleri kaydet, yükle ve sil |
| **Otomatik Kayıt** | Son script bir sonraki açılışta otomatik geri yüklenir |
| **Geri Al / Yenile** | Tam geri al/yenile geçmişi (butonlar + Ctrl+Z / Ctrl+Y) |
| **PDF Dışa Aktarma** | Scriptin yazdırmaya hazır PDF dışa aktarımı |
| **Dosya Yükleme** | Her kodlamada `.txt` (UTF-8, Latin-1, Windows-1252 …) + `.pdf` metin çıkarma |

## Gereksinimler

```bash
pip install PyQt5
```

**İsteğe bağlı ekstralar:**

```bash
pip install keyboard          # Global kısayollar (Linux'ta sudo gerekebilir)
pip install sounddevice numpy # Mikrofon otomatik hız
pip install PyMuPDF           # PDF metin içe aktarma
```

## Hızlı Başlangıç

```bash
python teleprompter.py
```

İki pencere yan yana otomatik olarak açılır:
- **Kontrol Paneli** — sol taraf, script editörü + tüm ayarlar
- **Prompter Ekranı** — sağ taraf, şeffaf bindirme (taşımak için sürükleyin, sağ alt köşeden yeniden boyutlandırın)

## Klavye Kısayolları

| Tuş | Eylem |
|---|---|
| `Boşluk` / `Enter` | Oynat / Duraklat |
| `↑` / `↓` | Hızı artır / azalt |
| `←` / `→` | Geri / ileri atla |
| `R` / `Esc` | Başa dön |
| Fare tekerleği | Hızı ayarla (prompter penceresinde) |

## Script Etiketleri

```
[PAUSE]         — kaydırma bu satırda otomatik durur
[[notunuz]]     — yalnızca Sunucu Notları penceresinde görünür
```

## Yapımcı

𝓐.𝓒.𝓑

## Lisans

MIT
