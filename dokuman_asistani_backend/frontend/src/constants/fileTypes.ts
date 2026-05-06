export const DOCVERSE_OFFICE_EXTENSIONS = [
  '.pdf',
  '.docx', '.doc', '.docm', '.dot', '.dotx', '.dotm', '.rtf', '.odt', '.ott', '.fodt', '.pages', '.wpd', '.wps',
  '.xlsx', '.xlsm', '.xls', '.xlt', '.xltx', '.xltm', '.xlsb', '.ods', '.ots', '.fods', '.numbers',
  '.pptx', '.ppt', '.pptm', '.pps', '.ppsx', '.ppsm', '.pot', '.potx', '.potm', '.odp', '.otp', '.fodp', '.key',
] as const;

export const DOCVERSE_DATA_EXTENSIONS = [
  '.csv', '.tsv', '.psv', '.json', '.jsonl', '.ndjson', '.xml', '.xsd', '.xsl', '.xslt', '.yaml', '.yml',
  '.toml', '.ini', '.cfg', '.conf', '.config', '.cnf', '.properties', '.prop', '.env', '.dotenv', '.lock',
  '.sql', '.sqlite', '.sqlite3', '.db', '.parquet', '.arrow', '.feather', '.h5', '.hdf5', '.sav', '.dta',
  '.sas7bdat', '.geojson', '.kml', '.kmz', '.shp', '.shx', '.dbf',
] as const;

export const DOCVERSE_CODE_EXTENSIONS = [
  '.html', '.htm', '.css', '.scss', '.sass', '.less', '.js', '.mjs', '.cjs', '.jsx', '.ts', '.tsx', '.vue',
  '.svelte', '.astro', '.py', '.pyw', '.pyi', '.java', '.kt', '.kts', '.scala', '.sc', '.groovy', '.gvy',
  '.go', '.rb', '.erb', '.rake', '.gemspec', '.php', '.phtml', '.c', '.h', '.cc', '.cpp', '.cxx', '.hh',
  '.hpp', '.hxx', '.cs', '.fs', '.fsx', '.vb', '.rs', '.swift', '.dart', '.lua', '.r', '.m', '.mm', '.pl',
  '.pm', '.erl', '.hrl', '.ex', '.exs', '.clj', '.cljs', '.cljc', '.hs', '.ml', '.mli', '.jl', '.nim',
  '.zig', '.sh', '.bash', '.zsh', '.fish', '.ps1', '.psm1', '.psd1', '.bat', '.cmd', '.graphql', '.gql',
  '.proto', '.thrift', '.avsc', '.dockerfile', '.dockerignore', '.gitignore', '.gitattributes',
  '.editorconfig', '.make', '.mk', '.cmake', '.gradle', '.sln', '.csproj', '.vbproj', '.fsproj',
  '.vcxproj', '.xcodeproj', '.pbxproj', '.pom',
] as const;

export const DOCVERSE_OCR_EXTENSIONS = [
  '.png', '.jpg', '.jpeg', '.jpe', '.webp', '.bmp', '.gif', '.tif', '.tiff', '.svg', '.svgz', '.heic',
  '.heif', '.avif', '.ico',
] as const;

export const DOCVERSE_MEDIA_EXTENSIONS = [
  '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.oga', '.opus', '.wma', '.amr',
  '.mp4', '.m4v', '.mov', '.avi', '.mkv', '.webm', '.wmv', '.flv', '.3gp', '.3g2',
  '.srt', '.vtt', '.ass', '.ssa',
] as const;

export const DOCVERSE_ARCHIVE_EXTENSIONS = ['.zip', '.tar', '.gz', '.tgz', '.bz2', '.tbz2', '.xz', '.txz', '.7z', '.rar'] as const;

export const DOCVERSE_BLOCKED_EXTENSIONS = [
  '.exe', '.dll', '.msi', '.com', '.scr', '.jar', '.war', '.ear', '.apk', '.ipa', '.app', '.deb', '.rpm',
  '.iso', '.img', '.bin', '.sys', '.drv', '.lnk', '.class',
] as const;

const TEXT_EXTENSIONS = [
  '.txt', '.text', '.md', '.markdown', '.mdown', '.mkd', '.rst', '.log', '.nfo', '.me', '.tex', '.latex',
  '.bib', '.adoc', '.asciidoc', '.org', '.textile', '.wiki',
] as const;
const NOTEBOOK_EXTENSIONS = ['.ipynb', '.rmd', '.qmd'] as const;
const EBOOK_EXTENSIONS = ['.epub', '.mobi', '.azw', '.azw3', '.fb2'] as const;
const DIAGRAM_EXTENSIONS = ['.drawio', '.dio', '.mmd', '.mermaid', '.puml', '.plantuml', '.vsdx', '.vsd'] as const;
const SCIENCE_EXTENSIONS = [
  '.pdb', '.pdbqt', '.sdf', '.mol', '.mol2', '.smi', '.smiles', '.cif', '.mmcif', '.xyz', '.gro', '.top',
  '.itp', '.mae', '.maegz',
] as const;

export const DOCVERSE_UPLOAD_EXTENSIONS = Array.from(
  new Set([
    ...DOCVERSE_OFFICE_EXTENSIONS,
    ...TEXT_EXTENSIONS,
    ...DOCVERSE_DATA_EXTENSIONS,
    ...NOTEBOOK_EXTENSIONS,
    ...EBOOK_EXTENSIONS,
    ...DOCVERSE_CODE_EXTENSIONS,
    ...DOCVERSE_OCR_EXTENSIONS,
    ...DOCVERSE_MEDIA_EXTENSIONS,
    ...DIAGRAM_EXTENSIONS,
    ...SCIENCE_EXTENSIONS,
    ...DOCVERSE_ARCHIVE_EXTENSIONS,
  ]),
).filter((extension) => !(DOCVERSE_BLOCKED_EXTENSIONS as readonly string[]).includes(extension));

export const DOCVERSE_PARSE_SUPPORTED_EXTENSIONS = [
  '.pdf', '.docx', '.xlsx', '.xlsm', '.pptx', '.doc', '.xls', '.ppt', '.txt', '.md', '.rst', '.log',
  '.csv', '.tsv', '.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.go', '.rb', '.php', '.c', '.cc', '.cpp',
  '.h', '.hpp', '.cs', '.sql', '.json', '.yml', '.yaml', '.html', '.css', '.xml', '.sh', '.ps1', '.bat',
  '.toml', '.ini', '.cfg', '.conf', '.env', '.rs', '.kt', '.swift', '.png', '.jpg', '.jpeg', '.webp',
  '.bmp', '.tif', '.tiff',
] as const;

export function normalizeExtension(ext: string) {
  const clean = ext.trim().toLowerCase();
  if (!clean) {
    return '';
  }
  return clean.startsWith('.') ? clean : `.${clean}`;
}

export function getFileExtension(filename: string) {
  const lower = filename.trim().toLowerCase();
  const special = ['.dockerfile', '.dockerignore', '.gitignore', '.gitattributes', '.editorconfig'];
  const matched = special.find((extension) => lower.endsWith(extension));
  if (matched) {
    return matched;
  }
  const index = lower.lastIndexOf('.');
  return index >= 0 ? lower.slice(index) : '';
}

export function isBlockedExtension(ext: string) {
  return (DOCVERSE_BLOCKED_EXTENSIONS as readonly string[]).includes(normalizeExtension(ext));
}

export function isAllowedUploadExtension(ext: string) {
  const normalized = normalizeExtension(ext);
  return (DOCVERSE_UPLOAD_EXTENSIONS as readonly string[]).includes(normalized) && !isBlockedExtension(normalized);
}

export function isParseSupportedExtension(ext: string) {
  return (DOCVERSE_PARSE_SUPPORTED_EXTENSIONS as readonly string[]).includes(normalizeExtension(ext));
}

export function getFileCategory(ext: string) {
  const normalized = normalizeExtension(ext);
  if (normalized === '.pdf') return 'pdf';
  if (['.docx', '.doc', '.docm', '.dot', '.dotx', '.dotm', '.rtf', '.odt', '.ott', '.fodt', '.pages', '.wpd', '.wps'].includes(normalized)) return 'word';
  if (['.xlsx', '.xlsm', '.xls', '.xlt', '.xltx', '.xltm', '.xlsb', '.ods', '.ots', '.fods', '.numbers'].includes(normalized)) return 'excel';
  if (['.pptx', '.ppt', '.pptm', '.pps', '.ppsx', '.ppsm', '.pot', '.potx', '.potm', '.odp', '.otp', '.fodp', '.key'].includes(normalized)) return 'powerpoint';
  if ((TEXT_EXTENSIONS as readonly string[]).includes(normalized)) return 'text';
  if ((DOCVERSE_CODE_EXTENSIONS as readonly string[]).includes(normalized)) return 'code';
  if ((DOCVERSE_DATA_EXTENSIONS as readonly string[]).includes(normalized)) return 'data';
  if ((DOCVERSE_OCR_EXTENSIONS as readonly string[]).includes(normalized)) return 'ocr';
  if (['.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.oga', '.opus', '.wma', '.amr'].includes(normalized)) return 'audio';
  if (['.mp4', '.m4v', '.mov', '.avi', '.mkv', '.webm', '.wmv', '.flv', '.3gp', '.3g2'].includes(normalized)) return 'video';
  if (['.srt', '.vtt', '.ass', '.ssa'].includes(normalized)) return 'subtitle';
  if ((SCIENCE_EXTENSIONS as readonly string[]).includes(normalized)) return 'science';
  if ((DOCVERSE_ARCHIVE_EXTENSIONS as readonly string[]).includes(normalized)) return 'archive';
  return 'other';
}

export function getFileCategoryLabel(ext: string) {
  const labels: Record<string, string> = {
    pdf: 'PDF',
    word: 'Word',
    excel: 'Excel',
    powerpoint: 'PowerPoint',
    text: 'Metin',
    code: 'Kod',
    data: 'Veri',
    ocr: 'Görsel/OCR',
    audio: 'Ses',
    video: 'Video',
    subtitle: 'Altyazı',
    science: 'Bilimsel',
    archive: 'Arşiv',
    other: 'Diğer',
  };
  return labels[getFileCategory(ext)] ?? 'Diğer';
}

export function getFileTypeWarning(ext: string) {
  const normalized = normalizeExtension(ext);
  if (isBlockedExtension(normalized)) {
    return 'Bu dosya türü güvenlik nedeniyle yüklenemez.';
  }
  if (!normalized || !isAllowedUploadExtension(normalized)) {
    return 'Bu dosya türü desteklenmiyor.';
  }
  if ((DOCVERSE_ARCHIVE_EXTENSIONS as readonly string[]).includes(normalized)) {
    return 'Arşiv dosyaları seçilebilir; içerik çıkarma desteği backend güvenlik kontrolüne bağlıdır.';
  }
  if (!isParseSupportedExtension(normalized)) {
    return 'Bu dosya yüklenebilir ancak şu anda içerik çıkarma desteği sınırlı olabilir.';
  }
  return null;
}

export function isUploadSelectionDisabled(ext: string) {
  const normalized = normalizeExtension(ext);
  return !normalized || isBlockedExtension(normalized) || !isAllowedUploadExtension(normalized);
}
