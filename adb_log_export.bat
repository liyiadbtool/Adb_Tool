@echo off
rem ======================================================================
rem  文件名 : adb_log_export.bat      版本 v3
rem  设计原则 : 输入侧 100% 遵循 adb / shell 原生语法，脚本只做
rem              (1) 跨命令保持当前目录  (2) 相对路径补全  (3) 输出排版适配
rem              不发明语法、不改命令语义，未识别的输入原样透传给设备 shell
rem  功  能 :
rem    1) 打开即进入设备目录（默认 /log/android_log/androidlog）
rem    2) 每次连接自动获取 root（成功静默，失败提示）
rem    3) 自动感知设备掉线 / 切换，并自动刷新
rem    4) cd 保持目录状态，语义同 shell（cd / cd .. / cd - / cd 绝对相对）
rem    5) ls 排版美化（横向多列、宽度自适应）；带选项（如 ls -l）原样透传
rem    6) 直接输入电脑路径（C:\XX、\\nas\share）回车即导出当前目录
rem    7) pull / push 与 adb 参数顺序一致，设备相对路径自动补全
rem    8) 其他任意命令（df、cat、ps、rm、mount ...）透传给 adb shell 执行
rem    9) 跳转快捷命令 res / logs（本质是 cd 别名，已在目标目录时不动）
rem   10) 裸 logcat 自动补 -d，避免流式输出把脚本卡住
rem  编  码 : ANSI/GBK + CRLF（中文 Windows 默认；另存为 UTF-8 会全屏乱码）
rem  平  台 : Windows 7 / 10 / 11，只需要 adb（platform-tools），不再依赖 PowerShell
rem  说  明 : 双击运行，或在 cmd 窗口里运行；不要用管道/重定向喂输入
rem ======================================================================
chcp 936 >nul 2>&1
rem 开启延迟展开（!VAR!）：用户可能输入带双引号/带空格的路径，
rem 用 %VAR% 把它们搬进 set "X=%VAR%" 会让 cmd 的引号配对失效、报"命令语法不正确"；
rem 延迟展开发生在语法分析之后，结果不会被再解释，才有办法原样搬运。
setlocal EnableDelayedExpansion

rem ------------------------- 可配置区 -------------------------
rem adb 可执行文件：已在 PATH 里就保持 adb；否则写完整路径（路径不要带空格）
set "ADB=adb"
rem 设备序列号：只连一台时留空；连多台必须填（用 adb devices 查看）
set "ADB_SERIAL="
rem 设备上的默认起始目录
set "ROOT=/log/android_log/androidlog"
rem 跳转快捷命令的目标目录：输入 res / logs 直接过去（命令名固定，路径可改）
rem 这两条只是 cd 的别名，不改变 adb / shell 的原生语法
set "JUMP_RES=/iflytek_a/iflytek/res"
set "JUMP_LOG=%ROOT%"
rem 连接时自动获取 root：1=开启（成功不提示，失败提示） 0=关闭
set "AUTO_ROOT=1"
rem 重连时轮询次数与间隔（秒）
set "RECONN_TRY=5"
rem 自动检测设备掉线/切换：1=开启 0=关闭（关闭后需手工输入 r）
set "WATCH_DEV=1"
rem ls 横向排版：每行最多显示几项（0=不限制，纯按窗口宽度）
set "LS_MAXCOL=10"
rem ls 横向排版：名称之间至少留几个空格
set "LS_GAP=3"
rem 取不到真实窗口宽度时的兜底列数
set "LS_WIDTH=100"
rem 导出落点：0=目标末段与目录名不同则套一层（如 C:\XX -> C:\XX\351）
rem           1=直接平铺进给定路径（不再多套一层）
set "EXPORT_FLAT=0"
rem ------------------------------------------------------------

set "TAG=%RANDOM%%RANDOM%"
set "OUTF=%TEMP%\adblg_%TAG%.txt"
set "OUTF2=%TEMP%\adblg2_%TAG%.txt"
rem 预置填充素材：100 个空格（供横向排版补齐用）
rem 注意：必须用 goto 循环，for /l 里的 %SPC% 只展开一次不会累积
set "SPC="
set /a _SI=0
:spc_loop
if %_SI% GEQ 100 goto spc_done
set "SPC=%SPC% "
set /a _SI+=1
goto spc_loop
:spc_done
rem 预置分隔线素材：200 个 = 与 200 个 -（一次生成，之后 bar 直接切前 N 个用）
set "_BEQ="
set "_BDASH="
set /a _SI=0
:bars_loop
if %_SI% GEQ 200 goto bars_done
set "_BEQ=%_BEQ%="
set "_BDASH=%_BDASH%-"
set /a _SI+=1
goto bars_loop
:bars_done
rem 窗口宽度留空：等 init_env / 第一次 ls 时真正取一次，之后整个会话复用
rem （窗口大小几乎不会中途变化，每次 ls 都跑一遍 mode con 是纯浪费）
set "LSW="

rem ==================== 一、启动 ====================
:boot
call :init_env
if errorlevel 1 goto boot_fail
goto main

rem ==================== 二、主循环 ====================
:main
rem 设备状态检查：上一条命令能成功执行就说明设备必然在线，跳过探测（省一次 adb 调用，
rem 这是每条命令都要付的固定开销）；只有上一条失败（可能掉线）时才真跑 adb devices
if "%WATCH_DEV%"=="1" if not "%CMD_OK%"=="1" call :watch_dev
rem 回到提示符前先把标记重置为"乐观"，等命令真正执行失败时再置 0
set "CMD_OK=1"

rem 先给 LINE 一个哨兵值：set /p 在"空回车"和"输入结束(Ctrl+Z)"下都不改变变量
rem 两种情况都无法直接区分，这里用连续 3 次空输入判定输入结束
set "LINE=##EOF##"
set /p "LINE=%CUR% > "

rem 安全闸门：& | < > 是 cmd 自己的语法字符，出现在参数里会把一行切成多条命令。
rem 延迟展开的值不会被再当成语法，所以这里做替换探测是安全的。
set "SPECHIT=0"
if not "!LINE!"=="!LINE:&=%!" set "SPECHIT=1"
if not "!LINE!"=="!LINE:|=%!" set "SPECHIT=1"
if not "!LINE!"=="!LINE:<=%!" set "SPECHIT=1"
if not "!LINE!"=="!LINE:>=%!" set "SPECHIT=1"
if "%SPECHIT%"=="1" goto arg_special_main

rem QC 只用于"是否电脑路径"的判断：先去引号，再去前导空白（含 Tab）
set "QC=!LINE:"=!"
if "%QC%"=="##EOF##" goto blank_line
for /f "tokens=*" %%a in ("%QC%") do set "QC=%%a"
if not defined QC goto blank_line
set /a BLANK_N=0

rem -------- 分支 0：整体是 Windows 本地路径 -> 导出当前目录 --------
rem 判定依据：第 2 个字符是冒号（盘符）或前两字符是双反斜杠（UNC）
rem 设备上的命令不可能以此开头，所以不会误伤
if "%QC:~1,1%"==":" goto exp_here
if "%QC:~0,2%"=="\\" goto exp_here

rem -------- 分词：拆出命令名与参数（容忍多空格） --------
call :split_line
if not defined CMD goto blank_line

rem -------- 分支 1：目录与列表 --------
if /i "%CMD%"=="cd" goto do_cd
if /i "%CMD%"=="pwd" goto do_pwd
if /i "%CMD%"=="ls" goto do_ls
if /i "%CMD%"=="lsf" goto do_lsf
rem 跳转快捷命令：res / logs 只在本脚本里存在，不占用设备上的任何命令名
rem （logcat 被设备占着，所以跳日志目录改用 logs，logcat 仍原样透传给设备）
if /i "%CMD%"=="res" goto do_jump_res
if /i "%CMD%"=="logs" goto do_jump_log

rem -------- 分支 2：文件传输 --------
if /i "%CMD%"=="pull" goto do_pull
if /i "%CMD%"=="push" goto do_push

rem -------- 分支 3：脚本快捷命令 --------
rem 说明：init / help 与设备上的真命令撞名，已分别让位给 ri / 设备 help
if /i "%CMD%"=="r" goto retry_soft
if /i "%CMD%"=="rl" goto retry_last
if /i "%CMD%"=="rr" goto retry_hard
if /i "%CMD%"=="ri" goto do_init
if /i "%CMD%"=="i" goto do_init
if /i "%CMD%"=="rw" goto do_rewidth
if /i "%CMD%"=="h" goto help
if "%CMD%"=="?" goto help
if /i "%CMD%"=="q" goto quit
if /i "%CMD%"=="quit" goto quit
if /i "%CMD%"=="exit" goto quit

rem -------- 分支 4：logcat 兜底（流式命令，裸跑会一直刷屏不返回） --------
if /i "%CMD%"=="logcat" goto do_logcat

rem -------- 分支 5：其余一律透传给设备 shell --------
goto do_pass

rem -------- 空回车 / 输入结束 --------
:blank_line
set /a BLANK_N+=1
if %BLANK_N% GEQ 3 goto input_end
goto main

:input_end
echo   输入已结束
goto quit

rem 主循环里拦到特殊字符：提示后回到提示符（goto main 而不是 exit /b，主循环不在 call 里）
:arg_special_main
call :arg_special
goto main

rem ==================== 三、输入解析 ====================
rem 输入：全局变量 LINE（整行原文）
rem 输出：CMD  命令名（第一个词）
rem       ARG  参数原文（可含空格与双引号，不做 trim）
rem       ARGQ 参数去掉全部双引号（供下游 if "%X%"=="..." 比较用）
rem
rem 这里刻意不从参数收值、也不比较"字符是不是双引号"：
rem   1) set "X=%~1" 在值里带双引号时会让引号配对失效，报"命令语法不正确"
rem   2) if "%_C%"==" " 在 _C 就是双引号时同样会炸
rem 所以全部改用延迟展开 !VAR!：它在语法分析之后才求值，结果不会再被当语法。
rem 只把半角空格当分隔符；用 Tab 分隔时整段透传给设备 shell 自己分词。
:split_line
set "CMD="
set "ARG="
set "ARGQ="
set "_S=!LINE!"
if not defined _S exit /b

:sll_lead
if not defined _S exit /b
set "_C=!_S:~0,1!"
if "!_C!"==" " (
    set "_S=!_S:~1!"
    goto sll_lead
)

:sll_word
if not defined _S exit /b
set "_C=!_S:~0,1!"
if "!_C!"==" " goto sll_arg
set "CMD=!CMD!!_C!"
set "_S=!_S:~1!"
goto sll_word

:sll_arg
:sll_argskip
if not defined _S exit /b
set "_C=!_S:~0,1!"
if not "!_C!"==" " goto sll_take
set "_S=!_S:~1!"
goto sll_argskip

:sll_take
set "ARG=!_S!"
rem 去掉全部双引号；含引号的值也能安全搬运（延迟展开不会被再当语法解释）
set "ARGQ=!ARG:"=!"
exit /b

:trim_tail
rem %1=变量名；去掉尾部的半角空格（用 call set 做间接取值）
call set "_T=%%%1%%"
if not defined _T exit /b
:tt_loop
if not "%_T:~-1%"==" " goto tt_done
set "_T=%_T:~0,-1%"
goto tt_loop
:tt_done
set "%1=%_T%"
exit /b

rem ==================== 四、cd / pwd ====================
:do_cd
if not defined ARG goto cd_home
rem 交给 cmd 的参数解析：自动处理引号与空格（cd "/log/my dir" 可用）
call :cd_target %ARG%
goto main

:cd_home
call :cd_do "~"
goto main

:cd_target
rem %1=目标目录（相对或绝对）；%~1 已剥掉外层引号
rem 本段由 call 进入，必须用 exit /b 返回；用 goto main 会残留 call 栈
if "%~1"=="-" goto cd_back
call :cd_do "%~1"
exit /b

:cd_back
if not defined OLDPWD goto cd_noprev
call :cd_do "%OLDPWD%"
exit /b

:cd_noprev
call :p_fail_msg "还没有上一个目录"
call :hint "先 cd 进任意目录，再用 cd - 返回"
exit /b

:cd_do
rem %1=目标；成功则更新 CUR / CNAME / OLDPWD，失败给出原因
rem 必须用 %~1：call 传参时 %1 带着引号，直接用会拼出 cd '"351"' 这种非法路径
set "CDARG=%~1"
rem 去尾随空格（此时 CDARG 已去引号，trim 是安全的）
call :trim_tail CDARG
if not defined CDARG exit /b
set "CDOLD=%CUR%"
rem 关键：pwd 带 -P，把设备返回的逻辑路径物理归一化，避免 ".." 残留
call :adb_call shell "cd '%CUR%' && cd '%CDARG%' && pwd -P" >"%OUTF%" 2>&1
set "RC=%ERRORLEVEL%"
set "NEWCUR="
for /f "usebackq delims=" %%L in ("%OUTF%") do call :take_first "%%L"

if %RC% NEQ 0 goto cd_fail
if not defined NEWCUR goto cd_fail
if not "%NEWCUR:~0,1%"=="/" goto cd_fail

call :norm_path "%NEWCUR%" NEWCUR
set "CUR=%NEWCUR%"
set "OLDPWD=%CDOLD%"
call :last_seg "%CUR%" CNAME
set "PEND_K="
rem 按 shell 习惯给不同的提示语
if "%CDARG:~0,2%"==".." goto cd_msg_up
if "%CDARG%"=="~" goto cd_msg_home
call :p_ok_msg "已进入 %CUR%"
goto cd_after

:cd_msg_up
call :p_ok_msg "已返回上级：%CUR%"
goto cd_after

:cd_msg_home
call :p_ok_msg "已回到家目录：%CUR%"

:cd_after
echo.
call :ls_render "%CUR%" "a"
exit /b

:cd_fail
set "PEND_K=CD"
rem 记下绝对路径（相对路径在这里补全），rl 才能准确重做
call :dev_abs "%~1" PEND_R
set "NEWCUR="
type "%OUTF%" | findstr /i /c:"Permission denied" >nul && goto cd_perm
type "%OUTF%" | findstr /i /c:"No such file" >nul && goto cd_nofile
type "%OUTF%" | findstr /i /c:"not a directory" >nul && goto cd_notdir
type "%OUTF%" | findstr /i /c:"not found" >nul && goto cd_disconn
call :p_fail_msg "进入失败：%CDARG%"
call :hint "用 ls 查看当前有哪些目录，或输入 r 重连后再试"
exit /b

:cd_perm
call :p_fail_msg "进入失败：Permission denied"
call :hint "该目录需要 root，输入 r 重新连接会自动获取 root 权限"
exit /b

:cd_nofile
call :p_fail_msg "进入失败：目录不存在 '%CDARG%'"
call :hint "用 ls 查看当前目录内容，或输入 r 重连后重试"
exit /b

:cd_notdir
call :p_fail_msg "进入失败：'%CDARG%' 不是目录"
call :hint "该路径是文件；用 lsf 查看同目录下的文件，或换一个目录"
exit /b

:cd_disconn
set "CMD_OK=0"
call :p_fail_msg "进入失败：设备连接中断"
call :hint "输入 rl 重试上次操作，或输入 r 刷新回到根目录"
exit /b

:do_pwd
echo   %CUR%
goto main

rem ==================== 四之二、跳转快捷命令 ====================
rem res / logs 只是 cd 的别名：目标写在顶部配置区，不带尾斜杠
rem 带参数时不跳转，原样透传（与 ls 的做法一致：只有"裸命令"才是快捷方式）
:do_jump_res
if defined ARG goto do_pass
call :jump_to "%JUMP_RES%" "res"
goto main

:do_jump_log
if defined ARG goto do_pass
call :jump_to "%JUMP_LOG%" "logs"
goto main

rem %1=目标绝对路径  %2=命令名（仅用于提示文案）
:jump_to
set "JTG=%~1"
set "JTN=%~2"
if not defined JTG goto jt_nocfg
rem 已经在目标目录：只给一行提示，不重查目录
rem （省一次 adb 调用，屏幕也不闪；这是"维持不变"的落点）
if /i "%CUR%"=="%JTG%" goto jt_same
rem 其他情况交给 cd_do：目录不存在/无权限/掉线由它统一诊断，失败时 CUR 保持不变
call :cd_do "%JTG%"
exit /b

:jt_same
call :p_info "已在 %JTG%，未跳转"
exit /b

:jt_nocfg
call :p_fail_msg "没有配置 %JTN% 的目标目录"
call :hint "在脚本顶部把 JUMP_RES / JUMP_LOG 填上路径，然后输入 ri 重连"
exit /b

rem ==================== 四之三、logcat 兜底 ====================
rem logcat 是流式命令，不按 Ctrl+C 就永不返回；裸跑会让脚本看起来卡死。
rem 规则与 ls 一致：只有"裸命令"才被脚本加工，带任何参数就原样透传给设备。
:do_logcat
if defined ARG goto do_pass
call :p_info "已自动加 -d：导出现有缓冲区后返回"
call :hint "要看实时日志请自己带参数，例如 logcat -v time（用 Ctrl+C 结束）"
set "ARG=-d"
set "ARGQ=-d"
goto do_pass

:arg_special
rem 由主循环的安全闸门 goto 过来（不在 call 里），所以这里只提示，返回交给调用方
call :p_fail_msg "输入里含有 & | < > 这些 cmd 语法字符，已中止"
call :hint "它们会被 cmd 当成分隔符，不经设备的 shell；请去掉或改名后再试"
exit /b

rem ==================== 五、ls / lsf ====================
:do_ls
rem 带选项（ls -l / ls -la / ls -R ...）一律原样透传给设备，保留系统原生格式
rem 用 ARGQ（已去引号）判断首字符：直接看 ARG 时值里带引号会让 if 的引号配对失效
if "%ARGQ:~0,1%"=="-" goto do_pass
if defined ARG goto ls_arg
call :ls_render "%CUR%" "a"
goto main
:ls_arg
call :ls_render_arg "%ARGQ%"
goto main

:ls_render_arg
call :ls_render "%~1" "a"
exit /b

:do_lsf
if defined ARG goto lsf_arg
call :ls_render "%CUR%" "f"
goto main
:lsf_arg
rem 借 cmd 的参数解析去掉引号、容忍空格
call :lsf_render_arg "%ARGQ%"
goto main

:lsf_render_arg
call :ls_render "%~1" "f"
exit /b

rem %1=路径（相对则相对当前目录） %2=a=全部 f=仅文件
:ls_render
set "LSP=%~1"
set "LMODE=%~2"
call :trim_tail LSP
if not defined LSP set "LSP=%CUR%"
if not defined LMODE set "LMODE=a"
rem 显示用前缀（相对路径时标出来，避免看混）
set "LSHEAD="
if /i not "%LSP%"=="%CUR%" set "LSHEAD=%LSP%"

rem 窗口宽度只取一次：init_env 已取过就直接复用（手动拖过窗口可输入 rw 重取）
if not defined LSW call :get_width

rem 取数据：全部用 ls -1（已排序、不含 . 与 ..，与 shell ls 一致）
rem         仅文件用 find -type f（设备普遍可用）
if /i "%LMODE%"=="f" goto lsr_find
call :adb_call shell "cd '%CUR%' && ls -1 '%LSP%' 2>&1" >"%OUTF%" 2>&1
set "RC=%ERRORLEVEL%"
goto lsr_check

:lsr_find
call :adb_call shell "cd '%CUR%' && find '%LSP%' -maxdepth 1 -type f 2>&1" >"%OUTF%" 2>&1
set "RC=%ERRORLEVEL%"

:lsr_check
if not exist "%OUTF%" goto ls_offline
rem 快路径：退出码 0 且输出非空 = 命令正常执行，不必逐条做错误诊断
rem （原来无条件跑 6 次 type^|findstr，每次都是两个进程，正常情况下全是白跑）
set /a FSZ=0
for %%f in ("%OUTF%") do set /a FSZ=%%~zf
if %RC% EQU 0 if %FSZ% GTR 0 goto lsr_scan
type "%OUTF%" | findstr /i /c:"Permission denied" >nul && goto ls_perm
type "%OUTF%" | findstr /i /c:"No such file" >nul && goto ls_nofile
type "%OUTF%" | findstr /i /c:"error: device" >nul && goto ls_offline
type "%OUTF%" | findstr /i /c:"device not found" >nul && goto ls_offline
type "%OUTF%" | findstr /i /c:"error: closed" >nul && goto ls_offline
type "%OUTF%" | findstr /i /c:"command not found" >nul && goto ls_nofind

:lsr_scan
rem 第一遍：求最长名字的字节宽度（GBK 下中文 2 字节 = 显示 2 列，正好对齐）
set /a MAXL=0
set /a CNT=0
for /f "usebackq delims=" %%L in ("%OUTF%") do call :ls_measure "%%L"

rem 一条都没解析出来且退出码非 0：说明命令本身失败了，不能当成空目录
if %CNT%==0 if %RC% NEQ 0 goto ls_error
if %CNT%==0 goto ls_empty

rem 列宽 = 最长名 + 间隔；可用宽度 = 窗口宽度 - 行首缩进 2
set /a CW=%MAXL%+%LS_GAP%
if %CW% LSS 4 set "CW=4"
set /a AVAIL=%LSW%-2
if %AVAIL% LSS %CW% set "AVAIL=%CW%"
set /a NC=%AVAIL%/%CW%
if %NC% LSS 1 set "NC=1"
if %LS_MAXCOL% GTR 0 if %NC% GTR %LS_MAXCOL% set "NC=%LS_MAXCOL%"

if not defined LSHEAD goto lsr_body
echo.
echo(  %LSHEAD%
:lsr_body
set /a COL=0
set /a PREV=0
set "ROW="
for /f "usebackq delims=" %%L in ("%OUTF%") do call :ls_emit "%%L"
if defined ROW echo(%ROW%
echo   共 %CNT% 项
exit /b

rem 第一遍：统计项数与最长名字宽度
:ls_measure
set "_N=%~1"
if not defined _N exit /b
if /i "%LMODE%"=="f" call :last_seg "%_N%" _N
if /i "%_N%"=="%LSP%" exit /b
set /a CNT+=1
call :strlen "%_N%" _LEN
if %_LEN% GTR %MAXL% set /a MAXL=%_LEN%
exit /b

rem 第二遍：横向排布输出
rem 一行的内容先拼进 ROW，满 NC 项再整行 echo
rem 不能用 set /p 逐项输出：set /p 会丢掉提示文本的前导空格，导致对齐全失效
:ls_emit
set "_N=%~1"
if not defined _N exit /b
if /i "%LMODE%"=="f" call :last_seg "%_N%" _N
if /i "%_N%"=="%LSP%" exit /b
call :strlen "%_N%" _LEN

if %COL% GEQ %NC% goto le_newline
if %COL%==0 (set "_LEAD=2") else (set /a _LEAD=%CW%-%PREV%)
if %_LEAD% LSS 1 set "_LEAD=1"
goto le_print

:le_newline
echo(%ROW%
set "ROW="
set /a COL=0
set "_LEAD=2"

:le_print
call set "_SP=%%SPC:~0,%_LEAD%%%"
rem 名字里的 & 交给 echo 前先转义，避免被当成命令分隔符
set "_NX=%_N%"
if not "%_NX%"=="%_NX:&=%" set "_NX=%_NX:&=^&%"
set "ROW=%ROW%%_SP%%_NX%"
set /a COL+=1
set "PREV=%_LEN%"
exit /b

:ls_empty
if not defined LSHEAD goto lse_1
echo.
echo(  %LSHEAD%
:lse_1
echo(  （空）
exit /b

:ls_perm
call :p_fail_msg "列目录失败：Permission denied"
call :hint "该目录需要 root，输入 r 重新连接会自动获取 root 权限"
exit /b

:ls_nofile
call :p_fail_msg "路径不存在：%LSP%"
call :hint "用 ls 查看当前目录内容，或输入 r 重连后重试"
exit /b

:ls_nofind
call :p_fail_msg "设备上没有 find 命令，无法列出文件"
call :hint "改用 ls 查看全部内容，或用 ls -l 查看详情"
exit /b

:ls_error
set "PEND_K=LS"
set "CMD_OK=0"
call :p_fail_msg "查询失败：未拿到任何结果（退出码 %RC%）"
call :hint "设备可能已断开或 adb 异常，输入 rl 重试，r 刷新回目录"
exit /b

:ls_offline
set "CMD_OK=0"
call :p_fail_msg "查询失败：设备连接中断"
call :hint "输入 rl 重试上次操作，或输入 r 刷新回到根目录"
exit /b

rem ==================== 六、直接输入电脑路径导出 ====================
:exp_here
rem QC 已去掉双引号与前导空白；这里再去尾部空白
set "EXP_Q=%QC%"
call :trim_tail EXP_Q
if not defined EXP_Q goto main
call :export "%CUR%" "%CNAME%" "%EXP_Q%"
goto main

rem %1=设备路径 %2=设备目录名 %3=电脑目标路径（已去引号）
:export
set "ERP=%~1"
set "ERN=%~2"
set "ERL=%~3"
rem 去尾随空格（此时已去引号，trim 安全）
call :trim_tail ERL
if not defined ERL goto exp_nopath

rem 去掉末尾多余的反斜杠（但保留盘符根目录的 C:\ 形式）
set "BS=\"
if not "%ERL:~-1%"=="%BS%" goto exp_notrail
if not "%ERL:~3%"=="" set "ERL=%ERL:~0,-1%"
if "%ERL:~1,1%"==":" if "%ERL:~2%"=="" set "ERL=%ERL%\%BS%"
:exp_notrail

if "%EXPORT_FLAT%"=="1" (
    set "ETARGET=%ERL%"
) else (
    rem 目标路径末段与设备目录名相同则直接铺进去，否则套一层同名目录
    set "ELNAME="
    for %%i in ("%ERL%") do set "ELNAME=%%~nxi"
    if /i "%ELNAME%"=="%ERN%" (
        set "ETARGET=%ERL%"
    ) else (
        if "%ERL:~-1%"=="%BS%" (set "ETARGET=%ERL%%ERN%") else (set "ETARGET=%ERL%\%ERN%")
    )
)

if not exist "%ETARGET%\" md "%ETARGET%" >nul 2>&1
if not exist "%ETARGET%\" goto exp_mkfail

echo   -^> %ETARGET%
call :adb_call pull "%ERP%" "%ETARGET%"
set "RC=%ERRORLEVEL%"
if %RC% NEQ 0 goto exp_fail

rem 统计落地文件数（递归统计，不用外部 find）
set /a FN=0
for /r "%ETARGET%" %%F in (*) do set /a FN+=1
if %FN%==0 goto exp_empty
set "PEND_K="
call :p_ok_msg "导出完成（%FN% 个文件）"
exit /b

:exp_empty
call :p_fail_msg "导出失败：没有取到任何文件"
call :hint "确认该目录里确实有文件，可用 lsf 查看同目录下的文件"
exit /b

:exp_nopath
call :p_fail_msg "导出失败：没有指定电脑上的目标路径"
call :hint "例如输入 C:\XX 或 D:\log"
exit /b

:exp_mkfail
call :p_fail_msg "导出失败：无法创建目录 %ETARGET%"
call :hint "检查路径拼写、盘符权限，或换一个目录"
exit /b

:exp_fail
set "PEND_K=PULL"
set "PEND_R=%ERP%"
set "PEND_N=%ERN%"
set "PEND_A=%ERL%"
set "CMD_OK=0"
call :p_fail_msg "导出失败：设备拉取出错（%ERP%）"
call :hint "输入 rl 可自动重试本次导出；先确认目录是否存在、是否需要 root"
exit /b

rem ==================== 七、pull / push ====================
rem 语义与 adb 一致：pull <设备路径> <电脑路径>   push <电脑路径> <设备路径>
:do_pull
if not defined ARG goto pull_usage_main
rem 借 cmd 自身的参数解析处理引号与空格：call :pull_run %ARG%
call :pull_run %ARG%
goto main

:pull_usage_main
call :pull_usage
goto main

:pull_run
rem %~1=设备路径 %~2=电脑路径
if "%~1"=="" goto pull_usage
if not "%~2"=="" goto pull_two
rem 只给了一个参数：若它是电脑路径，则导出当前目录（简写，非 adb 语法）
call :is_winpath "%~1"
if not defined ISWIN goto pull_need_path
call :export "%CUR%" "%CNAME%" "%~1"
exit /b

:pull_two
call :dev_abs "%~1" RMT
call :last_seg "%RMT%" RMS
call :export "%RMT%" "%RMS%" "%~2"
exit /b

:pull_usage
echo   用法：pull 设备路径 电脑路径
echo         例：pull 351 D:\log     （把设备上的 351 导出到 D:\log）
echo         简写：pull D:\log       （把当前目录导出到 D:\log）
exit /b

:pull_need_path
call :p_fail_msg "还差一个电脑路径"
call :hint "例：pull 351 D:\log"
exit /b

:do_push
if not defined ARG goto push_usage_main
call :push_run %ARG%
goto main

:push_usage_main
call :push_usage
goto main

:push_run
rem %~1=电脑路径 %~2=设备路径
if "%~1"=="" goto push_usage
if "%~2"=="" goto push_here
call :dev_abs "%~2" RMT
call :push_do "%~1" "%RMT%"
exit /b

:push_here
rem 只给一个参数：推到当前目录（简写）
call :push_do "%~1" "%CUR%"
exit /b

:push_do
rem %1=本地路径 %2=设备路径（调用时带引号，这里用 %~1 / %~2 去引号）
set "PL=%~1"
set "PR=%~2"
echo   -^> %PR%
call :adb_call push "%PL%" "%PR%"
set "RC=%ERRORLEVEL%"
if %RC% NEQ 0 goto push_fail
set "PEND_K="
call :p_ok_msg "推送完成"
exit /b

:push_fail
call :p_fail_msg "推送失败：adb push 出错"
call :hint "确认本地文件存在、设备目录可写（部分目录需要 root）"
exit /b

:push_usage
echo   用法：push 电脑路径 设备路径
echo         例：push D:\fix.sh /data/local/tmp/
echo         简写：push D:\fix.sh    （推到当前目录）
exit /b

rem ==================== 八、透传：交给设备 shell ====================
:do_pass
rem 用延迟展开拼：ARG 里可能带用户输入的双引号，%ARG% 搬进 set 会破坏引号配对
set "PC=!CMD!"
if defined ARG set "PC=!CMD! !ARG!"
rem 把内层双引号转义，保住外层这一对双引号，管道与重定向才能安全交给设备
set "PC=!PC:"=\"!"
call :adb_call shell "cd '%CUR%' && %PC%" >"%OUTF%" 2>&1
set "RC=%ERRORLEVEL%"

for %%f in ("%OUTF%") do if %%~zf==0 goto pass_maybe_silent
type "%OUTF%"
if %RC% NEQ 0 call :pass_rc
goto main

:pass_maybe_silent
if %RC%==0 goto main
call :pass_rc
goto main

:pass_rc
rem 本段由 call 进入，必须 exit /b
set "CMD_OK=0"
call :p_fail_msg "命令返回非 0（退出码 %RC%）"
call :hint "当前目录可能已失效，输入 r 刷新；或检查命令参数"
exit /b

rem ==================== 九、设备状态与刷新 ====================
:retry_soft
echo   [刷新] 等待设备上线 ...
set /a T=0
:rs_loop
call :scan_dev
if %DEVN% GTR 0 goto rs_ok
set /a T+=1
if %T% GEQ %RECONN_TRY% goto rs_bad
rem 用 ping 做延时：重定向环境下 timeout 会报错，ping 不会
ping -n 2 127.0.0.1 >nul 2>&1
goto rs_loop

:rs_ok
call :auto_root
set "CUR=%ROOT%"
call :last_seg "%CUR%" CNAME
set "OLDPWD="
call :probe
set "OFFLINE_FLAG=0"
set "CMD_OK=1"
call :p_ok_msg "已刷新，当前目录 %CUR%"
echo.
call :ls_render "%CUR%" "a"
goto main

:rs_bad
call :p_fail_msg "刷新失败：%RECONN_TRY% 次内设备都未上线"
call :hint "检查 USB 连接、手机授权弹窗，或输入 rr 重启 adb 服务"
goto main

:retry_hard
echo   [重连] 正在重启 adb 服务 ...
call :adb_call kill-server >nul 2>&1
call :adb_call start-server >nul 2>&1
echo   [重连] 完成
goto retry_soft

:retry_last
if not defined PEND_K goto rl_none
echo   [重试] 准备重做上次失败的操作 ...
set /a T=0
:rl_loop
call :scan_dev
if %DEVN% GTR 0 goto rl_ok
set /a T+=1
if %T% GEQ %RECONN_TRY% goto rl_bad
ping -n 2 127.0.0.1 >nul 2>&1
goto rl_loop

:rl_ok
call :auto_root
set "CMD_OK=1"
call :retry_pend
goto main

:rl_bad
call :p_fail_msg "重试失败：%RECONN_TRY% 次内设备都未上线"
call :hint "检查 USB 连接，或输入 rr 重启 adb 服务"
goto main

:rl_none
echo   没有可重试的操作
goto main

:retry_pend
if not defined PEND_K goto rp_none
if /i "%PEND_K%"=="CD" goto rp_cd
if /i "%PEND_K%"=="LS" goto rp_ls
if /i "%PEND_K%"=="PULL" goto rp_pull
goto rp_none

:rp_cd
echo   重做上次操作：cd %PEND_R%
call :cd_do "%PEND_R%"
exit /b

:rp_ls
echo   重做上次操作：ls
call :ls_render "%CUR%" "a"
exit /b

:rp_pull
echo   重做上次操作：导出 %PEND_R% -> %PEND_A%
call :export "%PEND_R%" "%PEND_N%" "%PEND_A%"
exit /b

:rp_none
exit /b

:do_rewidth
rem rw = 重新读取窗口宽度（拖过窗口后手工刷新；平时只在初始化时取一次）
set "LSW="
call :get_width
call :p_info "窗口宽度已重取：%LSW% 列"
goto main

:do_init
rem ri = 等同于重新打开脚本：清空全部状态、重新自检、重新取 root
echo   [初始化] 重新检测环境 ...
call :init_env
if errorlevel 1 goto init_fail
call :p_ok_msg "已初始化，当前目录 %CUR%"
goto main

:init_fail
echo   初始化未完成，设备不在线，可稍后输入 ri 重试
goto main

:watch_dev
rem 设备下线、上线、换机时自动刷新（每次一次 adb devices，耗时几十毫秒）
call :adb_call devices >"%OUTF%" 2>&1
set /a WN=0
set "WID="
for /f "usebackq skip=1 tokens=1,2" %%A in ("%OUTF%") do call :wd_count "%%A" "%%B"

if %WN%==0 goto wd_offline
if /i "%WID%"=="%DEVID%" if %WN%==%DEVN% if "%OFFLINE_FLAG%"=="0" exit /b
goto wd_switch

:wd_offline
if "%OFFLINE_FLAG%"=="1" exit /b
set "OFFLINE_FLAG=1"
echo.
echo   [设备] 已掉线（offline），操作会暂停；重新连上后自动刷新，无需重启
exit /b

:wd_switch
if not "%ADB_SERIAL%"=="" if /i not "%WID%"=="%ADB_SERIAL%" goto wd_conflict
set "CONFLICT_FLAG="
set "OLDID=%DEVID%"
set "DEVN=%WN%"
set "DEVID=%WID%"
set "OFFLINE_FLAG=0"
echo.
if /i "%OLDID%"=="%DEVID%" goto wd_back
echo   [设备] 已切换：%OLDID% -^> %DEVID%
goto wd_refresh

:wd_back
echo   [设备] 重新上线：%DEVID%

:wd_refresh
call :auto_root
rem 新设备上可能没有原路径，客户端要回到默认目录
call :adb_call shell "ls -d '%CUR%' 2>&1" >"%OUTF%" 2>&1
type "%OUTF%" | findstr /i /c:"No such file" >nul && goto wd_reset
type "%OUTF%" | findstr /i /c:"Permission denied" >nul && goto wd_reset
goto wd_keep

:wd_reset
set "OLDCUR=%CUR%"
set "CUR=%ROOT%"
call :last_seg "%CUR%" CNAME
echo   [设备] 新设备上没有 %OLDCUR%，已回到 %CUR%

:wd_keep
call :probe
call :p_ok_msg "已自动刷新，当前目录 %CUR%"
echo.
call :ls_render "%CUR%" "a"
exit /b

:wd_conflict
if "%CONFLICT_FLAG%"=="1" exit /b
set "CONFLICT_FLAG=1"
echo.
call :p_fail_msg "指定的序列号不在线：%ADB_SERIAL%"
call :hint "已检测到其它设备 %WID%；要切换请修改脚本顶部的 ADB_SERIAL，然后输入 ri"
exit /b

rem ==================== 十、底层调用与探测 ====================
:adb_call
rem 唯一的 adb 出口：所有 adb 命令都走这里，统一带 -s 参数与错误码
rem 用 call 调用：对 adb.exe 没有影响；若 ADB 被配置成 .bat/.cmd 包装脚本，
rem 也能正确返回（直接用 %ADB% 调用批处理会导致控制权不返回）
call "%ADB%"%SERIAL_OPT% %*
exit /b %ERRORLEVEL%

:init_env
rem 初始化 / 重新初始化：清状态 -> 自检 -> 找设备 -> 自动 root -> 探测目录 -> 横幅
set "PEND_K="
set "PEND_R="
set "PEND_N="
set "PEND_A="
set "OFFLINE_FLAG=0"
set "CONFLICT_FLAG="
set "ROOTOK="
set "PERMOK=1"
set "BLANK_N=0"
set "OLDPWD="
set "CUR=%ROOT%"

rem 初始化时强制重取窗口宽度（用户可能刚拖过窗口），清掉旧值再取
set "LSW="
call :get_width
call :adb_call version >nul 2>&1
if errorlevel 1 goto ie_noadb

rem 可选 -s 设备参数，前后预留空格方便拼接
set "SERIAL_OPT="
if not "%ADB_SERIAL%"=="" set "SERIAL_OPT= -s %ADB_SERIAL%"

call :scan_dev
if %DEVN%==0 goto ie_nodev
if %DEVN% GTR 1 if "%ADB_SERIAL%"=="" goto ie_multidev

call :auto_root
set "CUR=%ROOT%"
call :last_seg "%CUR%" CNAME
call :probe
rem 刚刚 scan_dev 成功，设备必然在线，别让主循环再探测一次
set "CMD_OK=1"
call :banner
exit /b 0

:ie_noadb
echo.
echo [错误] 无法执行 adb：%ADB%
echo        请安装 Android platform-tools 并加入 PATH；
echo        或把脚本顶部 ADB 改成 adb.exe 的完整路径（路径不要带空格）
exit /b 1

:ie_nodev
echo.
echo [错误] 没有检测到在线的设备
echo        1. 用数据线连接设备，确认已打开 USB 调试
echo        2. 在手机上的"允许调试"弹窗选始终允许
echo        3. 可在命令行执行 adb devices 确认状态为 device
exit /b 1

:ie_multidev
echo.
echo [错误] 检测到 %DEVN% 台设备，无法确定使用哪一台
echo        先执行 adb devices 查看序列号，填到脚本顶部的 ADB_SERIAL
exit /b 1

:scan_dev
call :adb_call devices >"%OUTF%" 2>&1
set /a DEVN=0
set "DEVID="
for /f "usebackq skip=1 tokens=1,2" %%A in ("%OUTF%") do call :dev_count "%%A" "%%B"
exit /b

:auto_root
rem 每次连接都尝试获取 root：成功静默，失败给出原因
if not "%AUTO_ROOT%"=="1" exit /b
call :adb_call root >"%OUTF%" 2>&1
rem adbd 重启期间会短暂 offline，等 1 秒再取状态
type "%OUTF%" | findstr /i /c:"restarting adbd as root" >nul && ping -n 2 127.0.0.1 >nul 2>&1

set /a AT=0
:ar_wait
call :adb_call get-state >"%OUTF2%" 2>&1
set "ST="
for /f "usebackq delims=" %%L in ("%OUTF2%") do call :take_st "%%L"
if /i "%ST%"=="device" goto ar_state
set /a AT+=1
if %AT% GEQ %RECONN_TRY% goto ar_nostate
ping -n 2 127.0.0.1 >nul 2>&1
goto ar_wait

:ar_state
type "%OUTF%" | findstr /i /c:"cannot run as root" >nul && goto ar_prod
type "%OUTF%" | findstr /i /c:"more than one device" >nul && goto ar_multi
type "%OUTF%" | findstr /i /c:"error:" >nul && goto ar_other
set "ROOTOK=1"
exit /b

:ar_prod
call :p_fail_msg "adb root 失败：adbd cannot run as root in production builds"
call :hint "普通 shell 权限可能读不到部分日志目录，需要换 userdebug/eng 版本"
exit /b

:ar_multi
call :p_fail_msg "adb root 失败：连接了多台设备，无法确定使用哪一台"
call :hint "在脚本顶部填写 ADB_SERIAL（用 adb devices 查看序列号），然后输入 ri"
exit /b

:ar_other
call :p_fail_msg "adb root 未成功：设备返回了错误"
call :hint "可能仍可用普通权限读取部分目录，请以实际操作结果为准"
exit /b

:ar_nostate
call :p_fail_msg "adb root 后设备未就绪（%RECONN_TRY% 次内未回到 device 状态）"
call :hint "输入 r 重试；一直不恢复请重插 USB，或输入 rr 重启 adb 服务"
exit /b

:probe
rem 探测当前目录能否读取（只做查询，不做任何修改）
call :adb_call shell "ls -d '%CUR%' 2>&1" >"%OUTF%" 2>&1
set "PERMOK=1"
type "%OUTF%" | findstr /i /c:"Permission denied" >nul && set "PERMOK=0"
type "%OUTF%" | findstr /i /c:"No such file" >nul && set "PERMOK=0"
exit /b

rem ==================== 十一、横幅与帮助 ====================
:banner
echo.
call :bar "="
rem 窄窗口（<76 列）下半版的两栏帮助会折行，改成单行紧凑版，避免糊成一团
if not defined LSW set "LSW=%LS_WIDTH%"
if %LSW% LSS 76 goto ban_narrow
echo   设备日志导出工具 v3                    [设备] %DEVN% 台在线  %DEVID%
call :bar "-"
echo   ls [目录] 列出全部（横排）      lsf [目录] 只列文件
echo   res 跳到 res 目录   logs 跳到日志目录（已在则不动）
echo   cd 目录 / cd .. / cd - / cd    进入、返回上级、返回上次、回家目录
echo   直接输入电脑路径（C:\XX）     把当前目录导出到该路径
echo   pull / push                    与 adb 参数顺序一致
echo   其他命令直接透传             如 df -h、cat build.prop、ps
echo   r=刷新  rl=重试上次  rr=重启adb  ri=初始化  rw=重取宽度  h=帮助  q=退出
goto ban_info

:ban_narrow
echo   设备日志导出工具 v3   [设备] %DEVN% 台在线
call :bar "-"
echo   ls / lsf / cd / cd .. / cd - / pull / push
echo   res / logs = 快捷跳转    其他命令透传给设备 shell
echo   h=帮助  q=退出

:ban_info
call :bar "="
if "%PERMOK%"=="0" (
    echo   [*] 目录读取受限：%CUR%
    echo       输入 r 重试；仍不行说明设备未 root 或日志目录属主限制
    echo.
)
echo   当前目录: %CUR%
if "%PERMOK%"=="1" call :ls_render "%CUR%" "a"
echo.
exit /b

:bar
rem %1=组成字符（= 或 -），输出一整行铺满窗口宽度
rem 用启动时预置好的整串切前 N 个，避免每次 bar 都循环 N 次拼字符串
set "BC=%~1"
if not defined BC set "BC=="
if not defined LSW set "LSW=%LS_WIDTH%"
set "_R=%LSW%"
if %_R% LSS 1 set "_R=1"
if %_R% GTR 200 goto bar_loop
if "%BC%"=="-" (echo(!_BDASH:~0,%_R%!) else (echo(!_BEQ:~0,%_R%!)
exit /b

rem 超长窗口（>200 列）兜底：老实循环拼
:bar_loop
set "_B="
:bar_add
if %_R% LEQ 0 goto bar_out
set "_B=%_B%%BC%"
set /a _R-=1
goto bar_add
:bar_out
echo %_B%
exit /b

:help
echo.
call :bar "-"
echo   目录与列表
echo     ls              列出当前目录的全部内容（横向多列，窗口宽度自适应）
echo     ls 351          列出子目录 351 的内容（不改变当前目录）
echo     ls -l / ls -la  带选项时原样交给设备，输出系统原生格式
echo     lsf [目录]      只列文件（确认某个 log 在不在）
echo     cd 目录         进入目录，例如 cd 351
echo     cd ..           返回上一级
echo     cd -            返回上一个目录
echo     cd              回到设备家目录（即 /）
echo     pwd             显示当前目录
echo     res             直接跳到 %JUMP_RES%
echo     logs            直接跳到 %JUMP_LOG%
echo                      （已经在目标目录时不跳转，只提示一句）
echo   文件传输
echo     C:\XX           把当前目录导出到 C:\XX（回车即执行）
echo     D:\log\351      目标末段与目录同名时直接铺进去，不套层
echo     pull 351 D:\log  导出指定目录（设备路径相对当前目录）
echo     pull D:\log      简写：导出当前目录
echo     push D:\fix.sh /data/local/tmp/    推送到设备
echo   其他命令
echo     df -h / cat 文件 / ps / rm / mkdir / mount ...  直接透传给设备 shell
echo     （透传命令的路径都相对于当前目录，不用每次写全路径）
echo     logcat          裸跑会自动加 -d（导完就返回，不会卡住）
echo                     带参数则原样交给设备；logcat -v time 是实时流，Ctrl+C 结束
echo   快捷命令
echo     r=刷新回根  rl=重试上次失败  rr=重启 adb 服务
echo     ri=完全初始化（等同重开脚本）  rw=重取窗口宽度
echo     h 或 ?=本帮助  q=退出
call :bar "-"
echo   提示：脚本全程不清屏，方便复制粘贴；不要用管道/重定向喂输入
echo         交互式命令（top 持续刷新、vi）请改用 top -n 1、cat 等一次性命令
echo.
goto main

:quit
echo   已退出。
del /f /q "%OUTF%" "%OUTF2%" >nul 2>&1
rem 双击运行时窗口会随进程关闭，这里补一个停顿，命令行下不停
echo("%CMDCMDLINE%"| findstr /i /c:"%~nx0" >nul && pause
endlocal
exit /b 0

:boot_fail
echo.
pause
endlocal
exit /b 1

rem ==================== 十二、字符串 / 路径工具 ====================
rem %1=字符串  %2=接收长度（字节数；GBK 下中文占 2）
:strlen
set "_S=%~1"
set "_L=0"
:stl_loop
if not defined _S goto stl_done
set "_S=%_S:~1%"
set /a _L+=1
goto stl_loop
:stl_done
set "%~2=%_L%"
exit /b

rem %1=窗口宽度获取：优先解析 mode con，失败用兜底值
rem 注意：中文系统输出"列:"，英文系统输出 Columns:，必须分两次独立 findstr
rem （多个 /c: 参数会让 findstr 破坏 GBK 字节，实测取不到值）
:get_width
set "LSW="
for /f "tokens=2" %%a in ('mode con ^<nul ^| findstr /c:"列"') do set "LSW=%%a"
if not defined LSW for /f "tokens=2" %%a in ('mode con ^<nul ^| findstr /i /c:"Columns"') do set "LSW=%%a"
if not defined LSW goto gw_default
call :is_digits "%LSW%"
if not defined ISNUM goto gw_default
if %LSW% LSS 40 goto gw_default
exit /b
:gw_default
set "LSW=%LS_WIDTH%"
exit /b

rem %1=字符串；纯数字（半角）则置 ISNUM=1，全角数字不算
:is_digits
set "ISNUM="
set "_S=%~1"
if not defined _S exit /b
rem 管道前的 % 紧贴 |，避免 echo 输出多余尾空格导致 $ 匹配失败
echo %_S%| findstr /r "^[0-9][0-9]*$" >nul && set "ISNUM=1"
exit /b

rem %1=参数  %2=接收：Windows 本地路径判定
:is_winpath
set "ISWIN="
set "_W=%~1"
if not defined _W exit /b
if "%_W:~1,1%"==":" set "ISWIN=1"
if "%_W:~0,2%"=="\\" set "ISWIN=1"
exit /b

rem %1=设备路径  %2=接收绝对路径（不以 / 开头则补当前目录）
:dev_abs
set "_D=%~1"
if "%_D:~0,1%"=="/" (set "%~2=%_D%") else (set "%~2=%CUR%/%_D%")
exit /b

rem %1=路径  %2=接收最后一段
:last_seg
set "_P=%~1"
:seg_loop
for /f "tokens=1,* delims=/" %%a in ("%_P%") do (
    if "%%b"=="" (set "%~2=%%a") else (set "_P=%%b" & goto seg_loop)
)
exit /b

rem %1=绝对路径  %2=接收去掉最后一段后的上级路径
:parent_seg
set "_P=%~1"
set "_OUT="
:ps_loop
for /f "tokens=1,* delims=/" %%a in ("%_P%") do (
    if "%%b"=="" (goto ps_done) else (set "_OUT=%_OUT%/%%a" & set "_P=%%b" & goto ps_loop)
)
:ps_done
if not defined _OUT set "_OUT=/"
set "%~2=%_OUT%"
exit /b

rem %1=路径  %2=接收归一化结果（按段扫描的栈式算法，多级 .. 也能算对）
:norm_path
set "_N=%~1"
set "_ACC="
:np_loop
if not defined _N goto np_fin
if "%_N%"=="/" goto np_fin
for /f "tokens=1,* delims=/" %%a in ("%_N%") do call :np_step "%%a" "%%b"
goto np_loop
:np_fin
if not defined _ACC set "_ACC=/"
set "%~2=%_ACC%"
exit /b

:np_step
set "_SEG=%~1"
set "_N=%~2"
if not defined _SEG exit /b
if "%_SEG%"=="." exit /b
if "%_SEG%"==".." goto np_pop
set "_ACC=%_ACC%/%_SEG%"
exit /b

:np_pop
if not defined _ACC exit /b
call :parent_seg "%_ACC%" _ACC
exit /b

rem %1=第一行  %2=接收（只取多行输出的第一行，并去掉尾部空格）
:take_first
if defined NEWCUR exit /b
set "_T=%~1"
:tf_trim
if not defined _T goto tf_done
if not "%_T:~-1%"==" " goto tf_done
set "_T=%_T:~0,-1%"
goto tf_trim
:tf_done
set "NEWCUR=%_T%"
exit /b

:take_st
if defined ST exit /b
set "ST=%~1"
exit /b

:dev_count
if not "%~2"=="device" exit /b
set /a DEVN+=1
if not defined DEVID set "DEVID=%~1"
exit /b

:wd_count
if not "%~2"=="device" exit /b
set /a WN+=1
if not defined WID set "WID=%~1"
exit /b

rem ==================== 十三、输出样式 ====================
rem √(U+221A) 与 ×(U+00D7) 在 GBK(936) 里就是 A1CC / A1C1，可以直接输出，
rem 不必为了一行彩色提示去启动 PowerShell（单次 300~800ms，是每条命令的固定开销）。
rem 代价是不上色，改用符号区分：√ 成功   × 失败   - 普通提示
rem 赋值用 %~1、回显用 !MSG!：消息里含 & 时也不会被当成命令分隔符
:p_ok_msg
set "MSG=%~1"
echo   √ !MSG!
exit /b

:p_fail_msg
set "MSG=%~1"
echo   × !MSG!
exit /b

:p_info
set "MSG=%~1"
echo   - !MSG!
exit /b

:hint
echo     %~1
exit /b
