"""
현재 포그라운드 창의 입력 언어(한글/영문)를 OS별로 감지한다.

[Windows IME 감지 방식]
일반적인 ImmGetContext → ImmGetConversionStatus 조합은
Electron(Claude Code)의 HWND에서 ImmGetContext가 0을 반환해 동작하지 않는다.

대신 ImmGetDefaultIMEWnd로 IME 전용 숨겨진 창 핸들을 얻은 뒤
WM_IME_CONTROL / IMC_GETCONVERSIONMODE 메시지를 전송해 변환 모드를 읽는다.
이 방식은 Electron 환경에서도 올바른 값을 반환한다.

변환 모드 비트:
  bit 0 (IME_CMODE_NATIVE, 0x1) = 1 → 한글 모드
  bit 0 = 0 → 영문(EN) 모드

[macOS 감지 방식]
Carbon 프레임워크의 TISCopyCurrentKeyboardInputSource()로 현재 입력 소스를 가져온 뒤
kTISPropertyInputSourceID 속성값에 'Korean'이 포함되면 한글 모드로 판단한다.
"""
import sys


def _get_ime_korean_win() -> bool:
    """포그라운드 창의 IME가 한글 모드이면 True를 반환한다. Windows 전용."""
    try:
        from ctypes import windll
        WM_IME_CONTROL        = 0x283
        IMC_GETCONVERSIONMODE = 0x001
        hwnd = windll.user32.GetForegroundWindow()
        ime_wnd = windll.imm32.ImmGetDefaultIMEWnd(hwnd)
        if not ime_wnd:
            return False
        conv = windll.user32.SendMessageW(ime_wnd, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
        return bool(conv & 0x1)
    except Exception:
        return False


def _get_ime_korean_mac() -> bool:
    """현재 키보드 입력 소스가 한글이면 True를 반환한다. macOS 전용."""
    try:
        from ctypes import cdll, c_void_p, c_char_p
        from ctypes.util import find_library

        carbon = cdll.LoadLibrary(find_library('Carbon'))
        carbon.TISCopyCurrentKeyboardInputSource.restype = c_void_p
        carbon.TISGetInputSourceProperty.restype = c_void_p
        carbon.TISGetInputSourceProperty.argtypes = [c_void_p, c_void_p]

        cf = cdll.LoadLibrary(find_library('CoreFoundation'))
        cf.CFStringGetCStringPtr.restype = c_char_p
        cf.CFStringGetCStringPtr.argtypes = [c_void_p, c_void_p]

        # kTISPropertyInputSourceID는 CFSTR로 정의된 상수이므로 직접 접근
        kTISPropertyInputSourceID = c_void_p.in_dll(carbon, 'kTISPropertyInputSourceID')

        source = carbon.TISCopyCurrentKeyboardInputSource()
        if not source:
            return False

        source_id_ref = carbon.TISGetInputSourceProperty(source, kTISPropertyInputSourceID)
        if not source_id_ref:
            return False

        # kCFStringEncodingUTF8 = 0x08000100
        source_id = cf.CFStringGetCStringPtr(source_id_ref, 0x08000100)
        if not source_id:
            return False

        return b'Korean' in source_id
    except Exception:
        return False


def _get_ime_korean() -> bool:
    if sys.platform == 'win32':
        return _get_ime_korean_win()
    elif sys.platform == 'darwin':
        return _get_ime_korean_mac()
    return False


def parse() -> bool:
    """현재 IME 상태를 파싱한다. True = 한글, False = 영문."""
    return _get_ime_korean()


def render(is_korean: bool, palette, style) -> str:
    """IME 상태를 statusline 문자열로 렌더링한다. 예: '🌍 한' / '🌍 EN'"""
    label = '한' if is_korean else 'EN'
    return f'🌍 {label}'
