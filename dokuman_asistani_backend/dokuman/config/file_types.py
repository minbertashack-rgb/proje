"""Guvenli upload uzanti kataloglari ve parser destek siniflandirmasi."""

DOCVERSE_OFFICE_EXTENSIONS = {
    ".pdf",
    ".docx", ".doc", ".docm", ".dot", ".dotx", ".dotm",
    ".rtf", ".odt", ".ott", ".fodt", ".pages", ".wpd", ".wps",
    ".xlsx", ".xlsm", ".xls", ".xlt", ".xltx", ".xltm", ".xlsb", ".ods", ".ots", ".fods", ".numbers",
    ".pptx", ".ppt", ".pptm", ".pps", ".ppsx", ".ppsm", ".pot", ".potx", ".potm", ".odp", ".otp", ".fodp", ".key",
}

DOCVERSE_TEXT_EXTENSIONS = {
    ".txt", ".text", ".md", ".markdown", ".mdown", ".mkd", ".rst", ".log", ".nfo", ".me",
    ".tex", ".latex", ".bib", ".adoc", ".asciidoc", ".org", ".textile", ".wiki",
}

DOCVERSE_DATA_EXTENSIONS = {
    ".csv", ".tsv", ".psv", ".json", ".jsonl", ".ndjson", ".xml", ".xsd", ".xsl", ".xslt",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".config", ".cnf", ".properties", ".prop",
    ".env", ".dotenv", ".lock", ".sql", ".sqlite", ".sqlite3", ".db", ".parquet", ".arrow", ".feather",
    ".h5", ".hdf5", ".sav", ".dta", ".sas7bdat", ".geojson", ".kml", ".kmz", ".shp", ".shx", ".dbf",
}

DOCVERSE_CODE_EXTENSIONS = {
    ".html", ".htm", ".css", ".scss", ".sass", ".less", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx",
    ".vue", ".svelte", ".astro", ".py", ".pyw", ".pyi", ".java", ".kt", ".kts", ".scala", ".sc",
    ".groovy", ".gvy", ".go", ".rb", ".erb", ".rake", ".gemspec", ".php", ".phtml", ".c", ".h",
    ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx", ".cs", ".fs", ".fsx", ".vb", ".rs", ".swift",
    ".dart", ".lua", ".r", ".m", ".mm", ".pl", ".pm", ".erl", ".hrl", ".ex", ".exs", ".clj",
    ".cljs", ".cljc", ".hs", ".ml", ".mli", ".jl", ".nim", ".zig", ".sh", ".bash", ".zsh",
    ".fish", ".ps1", ".psm1", ".psd1", ".bat", ".cmd", ".graphql", ".gql", ".proto", ".thrift",
    ".avsc", ".dockerfile", ".dockerignore", ".gitignore", ".gitattributes", ".editorconfig", ".make",
    ".mk", ".cmake", ".gradle", ".sln", ".csproj", ".vbproj", ".fsproj", ".vcxproj", ".xcodeproj",
    ".pbxproj", ".pom",
}

DOCVERSE_OCR_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".jpe", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".svg", ".svgz",
    ".heic", ".heif", ".avif", ".ico",
}

DOCVERSE_MEDIA_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma", ".amr",
    ".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".3gp", ".3g2",
    ".srt", ".vtt", ".ass", ".ssa",
}

DOCVERSE_SCIENCE_EXTENSIONS = {
    ".pdb", ".pdbqt", ".sdf", ".mol", ".mol2", ".smi", ".smiles", ".cif", ".mmcif", ".xyz",
    ".gro", ".top", ".itp", ".mae", ".maegz",
}

DOCVERSE_NOTEBOOK_EXTENSIONS = {".ipynb", ".rmd", ".qmd"}
DOCVERSE_EBOOK_EXTENSIONS = {".epub", ".mobi", ".azw", ".azw3", ".fb2"}
DOCVERSE_DIAGRAM_EXTENSIONS = {".drawio", ".dio", ".mmd", ".mermaid", ".puml", ".plantuml", ".vsdx", ".vsd"}
DOCVERSE_ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".tbz2", ".xz", ".txz", ".7z", ".rar"}

DOCVERSE_BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".msi", ".com", ".scr", ".jar", ".war", ".ear", ".apk", ".ipa", ".app",
    ".deb", ".rpm", ".iso", ".img", ".bin", ".sys", ".drv", ".lnk", ".class",
}

DOCVERSE_UPLOAD_EXTENSIONS = sorted(
    (
        DOCVERSE_OFFICE_EXTENSIONS
        | DOCVERSE_TEXT_EXTENSIONS
        | DOCVERSE_DATA_EXTENSIONS
        | DOCVERSE_CODE_EXTENSIONS
        | DOCVERSE_OCR_EXTENSIONS
        | DOCVERSE_MEDIA_EXTENSIONS
        | DOCVERSE_SCIENCE_EXTENSIONS
        | DOCVERSE_NOTEBOOK_EXTENSIONS
        | DOCVERSE_EBOOK_EXTENSIONS
        | DOCVERSE_DIAGRAM_EXTENSIONS
        | DOCVERSE_ARCHIVE_EXTENSIONS
    )
    - DOCVERSE_BLOCKED_EXTENSIONS
)

DOCVERSE_PARSE_SUPPORTED_EXTENSIONS = {
    ".pdf", ".docx", ".xlsx", ".xlsm", ".pptx",
    ".doc", ".xls", ".ppt",
    ".txt", ".md", ".rst", ".log",
    ".csv", ".tsv",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rb", ".php",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".sql", ".json", ".yml", ".yaml",
    ".html", ".css", ".xml", ".sh", ".ps1", ".bat", ".toml", ".ini", ".cfg", ".conf",
    ".env", ".rs", ".kt", ".swift",
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff",
}

PARSER_NOT_AVAILABLE_DETAIL = "Bu dosya türü yüklenebilir ancak şu anda içerik çıkarma desteği yok."


def normalize_extension(filename: str) -> str:
    name = str(filename or "").strip().lower()
    for special in (".dockerfile", ".dockerignore", ".gitignore", ".gitattributes", ".editorconfig"):
        if name.endswith(special):
            return special
    if "." not in name:
        return ""
    return "." + name.rsplit(".", 1)[1]


def category_for_extension(ext: str) -> str:
    clean = str(ext or "").lower()
    if clean == ".pdf":
        return "PDF"
    if clean in {".docx", ".doc", ".docm", ".dot", ".dotx", ".dotm", ".rtf", ".odt", ".ott", ".fodt", ".pages", ".wpd", ".wps"}:
        return "Word"
    if clean in {".xlsx", ".xlsm", ".xls", ".xlt", ".xltx", ".xltm", ".xlsb", ".ods", ".ots", ".fods", ".numbers"}:
        return "Excel"
    if clean in {".pptx", ".ppt", ".pptm", ".pps", ".ppsx", ".ppsm", ".pot", ".potx", ".potm", ".odp", ".otp", ".fodp", ".key"}:
        return "PowerPoint"
    if clean in DOCVERSE_TEXT_EXTENSIONS:
        return "Metin"
    if clean in DOCVERSE_CODE_EXTENSIONS:
        return "Kod"
    if clean in DOCVERSE_DATA_EXTENSIONS:
        return "Veri"
    if clean in DOCVERSE_OCR_EXTENSIONS:
        return "Görsel/OCR"
    if clean in {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wma", ".amr"}:
        return "Ses"
    if clean in {".mp4", ".m4v", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".3gp", ".3g2"}:
        return "Video"
    if clean in {".srt", ".vtt", ".ass", ".ssa"}:
        return "Altyazı"
    if clean in DOCVERSE_SCIENCE_EXTENSIONS:
        return "Bilimsel"
    if clean in DOCVERSE_ARCHIVE_EXTENSIONS:
        return "Arşiv"
    return "Diğer"
