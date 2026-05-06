# Mini Varlik Havuzu

Bu klasor, parser ve ingestion regression testlerinde kullanilan
gercek-belge-benzeri mini belge senaryolarini tutar.

Belgeler repoya binary olarak eklenmiyor; senaryo tanimlari
`mini_varlik_havuzu.py` icinde tutuluyor ve test sirasinda kucuk
PDF/DOCX fixture dosyalarina donusturuluyor.

Guvence verdigi baslik riskleri:

- intro path ile ilk heading path cakismasi
- buyuk harfli paragrafi heading sanma
- kisa gercek basliklari kaybetme
- karmasik DOCX duzeninde asiri bolunme
- zayif icerikte sahte `parcalandi`
