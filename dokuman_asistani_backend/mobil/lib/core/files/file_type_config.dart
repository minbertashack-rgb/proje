class FileTypeInfo {
  const FileTypeInfo({
    required this.extension,
    required this.category,
    required this.uploadAllowed,
    required this.parseSupported,
    this.blocked = false,
    this.archive = false,
  });

  final String extension;
  final String category;
  final bool uploadAllowed;
  final bool parseSupported;
  final bool blocked;
  final bool archive;
}

const blockedExtensions = <String>{
  'exe', 'dll', 'msi', 'com', 'scr', 'jar', 'war', 'ear', 'apk', 'ipa', 'app',
  'deb', 'rpm', 'iso', 'img', 'bin', 'sys', 'drv', 'lnk', 'class',
};

const uploadExtensions = <String>[
  'pdf',
  'docx', 'doc', 'docm', 'dot', 'dotx', 'dotm', 'rtf', 'odt', 'ott', 'fodt', 'pages', 'wpd', 'wps',
  'xlsx', 'xlsm', 'xls', 'xlt', 'xltx', 'xltm', 'xlsb', 'ods', 'ots', 'fods', 'numbers',
  'pptx', 'ppt', 'pptm', 'pps', 'ppsx', 'ppsm', 'pot', 'potx', 'potm', 'odp', 'otp', 'fodp', 'key',
  'txt', 'text', 'md', 'markdown', 'mdown', 'mkd', 'rst', 'log', 'nfo', 'me', 'tex', 'latex', 'bib',
  'adoc', 'asciidoc', 'org', 'textile', 'wiki',
  'csv', 'tsv', 'psv', 'json', 'jsonl', 'ndjson', 'xml', 'xsd', 'xsl', 'xslt', 'yaml', 'yml',
  'toml', 'ini', 'cfg', 'conf', 'config', 'cnf', 'properties', 'prop', 'env', 'dotenv', 'lock',
  'sql', 'sqlite', 'sqlite3', 'db', 'parquet', 'arrow', 'feather', 'h5', 'hdf5', 'sav', 'dta', 'sas7bdat',
  'ipynb', 'rmd', 'qmd', 'epub', 'mobi', 'azw', 'azw3', 'fb2',
  'html', 'htm', 'css', 'scss', 'sass', 'less', 'js', 'mjs', 'cjs', 'jsx', 'ts', 'tsx', 'vue', 'svelte', 'astro',
  'py', 'pyw', 'pyi', 'java', 'kt', 'kts', 'scala', 'sc', 'groovy', 'gvy', 'go', 'rb', 'erb', 'rake', 'gemspec',
  'php', 'phtml', 'c', 'h', 'cc', 'cpp', 'cxx', 'hh', 'hpp', 'hxx', 'cs', 'fs', 'fsx', 'vb', 'rs', 'swift',
  'dart', 'lua', 'r', 'm', 'mm', 'pl', 'pm', 'erl', 'hrl', 'ex', 'exs', 'clj', 'cljs', 'cljc', 'hs', 'ml',
  'mli', 'jl', 'nim', 'zig',
  'sh', 'bash', 'zsh', 'fish', 'ps1', 'psm1', 'psd1', 'bat', 'cmd',
  'graphql', 'gql', 'proto', 'thrift', 'avsc', 'dockerfile', 'dockerignore', 'gitignore', 'gitattributes',
  'editorconfig', 'make', 'mk', 'cmake', 'gradle', 'sln', 'csproj', 'vbproj', 'fsproj', 'vcxproj', 'xcodeproj',
  'pbxproj', 'pom',
  'png', 'jpg', 'jpeg', 'jpe', 'webp', 'bmp', 'gif', 'tif', 'tiff', 'svg', 'svgz', 'heic', 'heif', 'avif', 'ico',
  'mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'oga', 'opus', 'wma', 'amr',
  'mp4', 'm4v', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'flv', '3gp', '3g2',
  'srt', 'vtt', 'ass', 'ssa', 'drawio', 'dio', 'mmd', 'mermaid', 'puml', 'plantuml', 'vsdx', 'vsd',
  'geojson', 'kml', 'kmz', 'shp', 'shx', 'dbf',
  'pdb', 'pdbqt', 'sdf', 'mol', 'mol2', 'smi', 'smiles', 'cif', 'mmcif', 'xyz', 'gro', 'top', 'itp', 'mae', 'maegz',
  'zip', 'tar', 'gz', 'tgz', 'bz2', 'tbz2', 'xz', 'txz', '7z', 'rar',
];

const parseSupportedExtensions = <String>{
  'pdf', 'docx', 'xlsx', 'xlsm', 'pptx', 'doc', 'xls', 'ppt',
  'txt', 'md', 'rst', 'log', 'csv', 'tsv',
  'py', 'js', 'ts', 'tsx', 'jsx', 'java', 'go', 'rb', 'php', 'c', 'cc',
  'cpp', 'h', 'hpp', 'cs', 'sql', 'json', 'yml', 'yaml', 'html', 'css',
  'xml', 'sh', 'ps1', 'bat', 'toml', 'ini', 'cfg', 'conf', 'env', 'rs',
  'kt', 'swift', 'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tif', 'tiff',
};

const archiveExtensions = <String>{'zip', 'tar', 'gz', 'tgz', 'bz2', 'tbz2', 'xz', 'txz', '7z', 'rar'};

String normalizeFileExtension(String? value) {
  final raw = (value ?? '').trim().toLowerCase();
  if (raw.isEmpty) return '';
  final withoutDot = raw.startsWith('.') ? raw.substring(1) : raw;
  return withoutDot;
}

String categoryForExtension(String extension) {
  final ext = normalizeFileExtension(extension);
  if (ext == 'pdf') return 'PDF';
  if ({'docx', 'doc', 'docm', 'dot', 'dotx', 'dotm', 'rtf', 'odt', 'ott', 'fodt', 'pages', 'wpd', 'wps'}.contains(ext)) return 'Word';
  if ({'xlsx', 'xlsm', 'xls', 'xlt', 'xltx', 'xltm', 'xlsb', 'ods', 'ots', 'fods', 'numbers'}.contains(ext)) return 'Excel';
  if ({'pptx', 'ppt', 'pptm', 'pps', 'ppsx', 'ppsm', 'pot', 'potx', 'potm', 'odp', 'otp', 'fodp', 'key'}.contains(ext)) return 'PowerPoint';
  if ({'txt', 'text', 'md', 'markdown', 'mdown', 'mkd', 'rst', 'log', 'nfo', 'me', 'tex', 'latex', 'bib', 'adoc', 'asciidoc', 'org', 'textile', 'wiki'}.contains(ext)) return 'Metin';
  if ({'png', 'jpg', 'jpeg', 'jpe', 'webp', 'bmp', 'gif', 'tif', 'tiff', 'svg', 'svgz', 'heic', 'heif', 'avif', 'ico'}.contains(ext)) return 'Görsel/OCR';
  if ({'mp3', 'wav', 'm4a', 'aac', 'flac', 'ogg', 'oga', 'opus', 'wma', 'amr'}.contains(ext)) return 'Ses';
  if ({'mp4', 'm4v', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'flv', '3gp', '3g2'}.contains(ext)) return 'Video';
  if ({'srt', 'vtt', 'ass', 'ssa'}.contains(ext)) return 'Altyazı';
  if (archiveExtensions.contains(ext)) return 'Arşiv';
  if ({'pdb', 'pdbqt', 'sdf', 'mol', 'mol2', 'smi', 'smiles', 'cif', 'mmcif', 'xyz', 'gro', 'top', 'itp', 'mae', 'maegz'}.contains(ext)) return 'Bilimsel';
  if (uploadExtensions.contains(ext) && !parseSupportedExtensions.contains(ext)) return 'Diğer';
  return 'Kod';
}

FileTypeInfo fileTypeInfoForExtension(String? extension) {
  final ext = normalizeFileExtension(extension);
  final blocked = blockedExtensions.contains(ext);
  final allowed = uploadExtensions.contains(ext) && !blocked;
  return FileTypeInfo(
    extension: ext,
    category: ext.isEmpty ? 'Diğer' : categoryForExtension(ext),
    uploadAllowed: allowed,
    parseSupported: parseSupportedExtensions.contains(ext),
    blocked: blocked,
    archive: archiveExtensions.contains(ext),
  );
}
