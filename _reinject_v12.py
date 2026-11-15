# -*- coding: utf-8 -*-
"""只重灌 CSS / 字体 / JS 三个块（结构块已在 ui.html 里，不动）。"""
import io, os, re
ROOT = r'C:/Users/李亦/Desktop/Adb_Tool'
UI = os.path.join(ROOT, 'adb_log_gui', 'webview2', 'ui.html')
s = io.open(UI, encoding='utf-8').read()
s = re.sub(r'/\* === V12 FONTS START ===.*?/\* === V12 FONTS END === \*/\n', '', s, flags=re.S)
s = re.sub(r'/\* === V12 LAYER START === \*/.*?/\* === V12 LAYER END === \*/\n', '', s, flags=re.S)
s = re.sub(r'/\* === V12 JS START ===.*?/\* === V12 JS END === \*/\n', '', s, flags=re.S)
fonts = io.open(os.path.join(ROOT, '_v12_fonts.css'), encoding='utf-8').read()
css = io.open(os.path.join(ROOT, '_v12.css'), encoding='utf-8').read()
js = io.open(os.path.join(ROOT, '_v12.js'), encoding='utf-8').read()
assert s.count('</style>') == 1 and s.count('\n</script>') == 1
s = s.replace('</style>', fonts + css + '</style>', 1)
s = s.replace('\n</script>', '\n' + js + '\n</script>', 1)
io.open(UI, 'w', encoding='utf-8', newline='').write(s)
print('reinjected, %.1f KB' % (len(s) / 1024.0))
