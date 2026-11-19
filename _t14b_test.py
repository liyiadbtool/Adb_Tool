# -*- coding: utf-8 -*-
"""T14b：文件交互第一批的回归断言。"""
import io

P = r"C:\Users\SunWwei\Desktop\Adb_Tool\377\_test_file_ui.py"
s = io.open(P, encoding="utf-8").read()

anchor = """    ok('T14a 重试后清掉错误并回到 loading',
       _fs.dev.nodes['/sdcard'].err === '' && _fs.dev.nodes['/sdcard'].loading === true);"""

add = anchor + """

    /* ---------- T14b（2026-11-19）：文件交互第一批 ---------- */
    // 造一组含隐藏文件、大小/时间不同的兄弟节点
    onFsList({ kind:'fslist', seq: 999, side:'dev', path:'/sdcard', parent:'/',
               err:'', items:[
                 {name:'b.apk',  path:'/sdcard/b.apk',  dir:false, size:300, time:'2026-11-02 10:00', perm:'', sizeText:'300 B'},
                 {name:'.hidden',path:'/sdcard/.hidden',dir:false, size:1,   time:'2026-11-03 10:00', perm:'', sizeText:'1 B'},
                 {name:'a.log',  path:'/sdcard/a.log',  dir:false, size:900, time:'2026-11-01 10:00', perm:'', sizeText:'900 B'},
                 {name:'sub',    path:'/sdcard/sub',    dir:true,  size:0,   time:'2026-11-04 10:00', perm:'', sizeText:''}
               ]});

    // ③ 默认不显示点文件
    ok('T14b 默认隐藏点文件', !hasRow('dev','/sdcard/.hidden'));
    fsToggleHidden('dev');
    ok('T14b 打开后显示点文件', hasRow('dev','/sdcard/.hidden'));
    fsToggleHidden('dev');
    ok('T14b 可再关掉', !hasRow('dev','/sdcard/.hidden'));

    // ⑧ 排序：目录恒在前；按大小升/降序
    fsSortBy('dev', 'size');
    var order1 = fsKids(_fs.dev, _fs.dev.nodes['/sdcard'].children).map(function(e){ return e.name; });
    ok('T14b 按大小升序且目录在前', order1[0] === 'sub' && order1[1] === 'b.apk' && order1[2] === 'a.log',
       order1.join(','));
    fsSortBy('dev', 'size');
    var order2 = fsKids(_fs.dev, _fs.dev.nodes['/sdcard'].children).map(function(e){ return e.name; });
    ok('T14b 再点一次切降序', order2[1] === 'a.log' && order2[2] === 'b.apk', order2.join(','));
    fsSortBy('dev', 'name');
    ok('T14b 排序切回名称升序',
       fsKids(_fs.dev, _fs.dev.nodes['/sdcard'].children)[1].name === 'a.log');

    // ② Shift 连选：先点 b.apk，再 Shift 点 sub（可见顺序 b.apk → a.log → sub）
    _fs.dev.sel = {};
    fsClick('dev', rowByPath('dev','/sdcard/b.apk'), {});
    fsClick('dev', rowByPath('dev','/sdcard/sub'), { shiftKey: true });
    var selN = fsSelectedPaths('dev').length;
    ok('T14b Shift 连选选中区间', selN >= 2, '选中 ' + selN + ' 项');

    // ① 右键菜单
    _fs.dev.sel = {};
    fsCtxOpen({ preventDefault:function(){}, stopPropagation:function(){} },
              'dev', '/sdcard/a.log');
    var menu = document.querySelector('.fs-ctx');
    ok('T14b 右键弹出菜单', !!menu, menu ? 'ok' : '没有菜单');
    ok('T14b 设备侧菜单有「下载到本机」',
       menu && menu.textContent.indexOf('下载到本机') >= 0,
       menu ? menu.textContent.slice(0, 40) : '');
    ok('T14b 菜单里有重命名/删除/复制路径/新建文件夹',
       menu && menu.textContent.indexOf('重命名') >= 0
       && menu.textContent.indexOf('删除') >= 0
       && menu.textContent.indexOf('复制路径') >= 0
       && menu.textContent.indexOf('新建文件夹') >= 0);
    ok('T14b 右键会把该行选中', _fs.dev.sel[fsNorm('/sdcard/a.log')] === 1);
    Overlay.close();

    // ⑤ 路径栏双击可编辑
    fsPathEdit({ preventDefault:function(){}, stopPropagation:function(){} }, 'dev');
    var pin = document.querySelector('#crumb-dev .fs-pathin');
    ok('T14b 双击面包屑出现路径输入框', !!pin, pin ? 'ok' : '没有输入框');
    if (pin) {
      SENT.length = 0;
      pin.value = '/data/local/tmp';
      pin.dispatchEvent(new KeyboardEvent('keydown', { key:'Enter', bubbles:true }));
      ok('T14b 输入路径回车发起请求',
         !!last('fslist') && last('fslist').path === '/data/local/tmp',
         JSON.stringify(last('fslist')));
    }"""

assert s.count(anchor) == 1, "锚点没匹配上"
s = s.replace(anchor, add)
io.open(P, "w", encoding="utf-8", newline="\n").write(s)
print("T14b 断言已加")
