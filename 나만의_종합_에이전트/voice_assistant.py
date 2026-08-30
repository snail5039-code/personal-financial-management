"""음성 웨이크워드 - "커리마"라고 부르면 듣고 있다가 명령을 처리한다.

openWakeWord 같은 전용 웨이크워드 엔진은 무료로 쓸 수 있는 게 영어 단어(예: "Hey Jarvis")뿐이고,
Vosk 같은 전통 방식 한국어 인식기는 정해진 단어 사전 안에서만 인식해서 "커리마"처럼 사전에 없는
이름은 구조적으로 인식이 안 된다. 그래서 faster-whisper(신경망 기반, 사전에 없는 말도 소리 그대로
옮길 수 있음)로 짧은 구간을 계속 녹음·인식하면서 "커리마"와 발음이 비슷한지 직접 비교한다.
전용 엔진보다 CPU를 더 쓰는 대신, 실제 부르고 싶은 이름을 그대로 쓸 수 있다.
"""

import os

# Whisper 모델을 처음 받을 때 huggingface_hub가 캐시를 심볼릭 링크로 관리하려 하는데,
# Windows에서 개발자 모드/관리자 권한이 없으면 심볼릭 링크 생성이 막혀서 다운로드가 그대로
# 실패한다. 파일을 복사하는 방식으로 강제해서 별도 설정 없이도 되게 한다. faster_whisper를
# import하기 전에 설정해야 huggingface_hub가 이 값을 읽는다.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")

import json
import re
import winsound

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

import app as kurima_app
import tools

SAMPLE_RATE = 16000
WAKE_WORD = "커리마"
WAKE_CHUNK_SECONDS = 2.5
COMMAND_SECONDS = 5.0
CONFIRM_ANSWER_SECONDS = 3.0
_AFFIRMATIVE_WORDS = ("네", "예", "응", "어", "그래", "오케이", "좋아", "진행", "실행", "맞아")
# 웨이크워드 판정 관대함 정도. 합성 음성 테스트에서 "코리마"/"꼬리마"처럼 한 글자 정도
# 다르게 들리는 경우가 있어서, 편집거리 1까지는 같은 말로 본다.
MAX_EDIT_DISTANCE = 1

_wake_model = None
_command_model = None


def _get_wake_model():
    """웨이크워드 판정용. 'tiny'는 빠르지만 3글자짜리 만든 단어에서 오인식이 잦아서
    'base'로 정확도와 속도를 절충한다."""
    global _wake_model
    if _wake_model is None:
        _wake_model = WhisperModel("base", device="cpu", compute_type="int8")
    return _wake_model


def _get_command_model():
    """실제 명령 인식용 - Gemini에 넘길 문장이라 정확도를 더 챙긴다."""
    global _command_model
    if _command_model is None:
        _command_model = WhisperModel("small", device="cpu", compute_type="int8")
    return _command_model


def _record(seconds):
    audio = sd.rec(int(seconds * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    return _normalize_volume(audio)


# 명령/확인 대답은 사람마다 말하는 길이가 다른데, 매번 고정된 초만큼 녹음하면 짧게 말하고도
# 남은 시간을 그냥 흘려보내야 해서 체감 반응이 느려진다. 짧은 구간(프레임) 단위로 녹음하면서
# 말이 시작된 뒤 조용한 구간이 이어지면 그 자리에서 바로 멈춘다.
_FRAME_SECONDS = 0.2
_SILENCE_HANG_SECONDS = 0.6
_SPEECH_START_PEAK = 250


def _record_until_silence(max_seconds):
    frame_samples = int(_FRAME_SECONDS * SAMPLE_RATE)
    silence_frames_needed = max(1, int(_SILENCE_HANG_SECONDS / _FRAME_SECONDS))
    max_frames = max(1, int(max_seconds / _FRAME_SECONDS))

    frames = []
    speech_started = False
    silence_run = 0
    for _ in range(max_frames):
        frame = sd.rec(frame_samples, samplerate=SAMPLE_RATE, channels=1, dtype="int16")
        sd.wait()
        frames.append(frame)

        if int(np.abs(frame).max()) >= _SPEECH_START_PEAK:
            speech_started = True
            silence_run = 0
        elif speech_started:
            silence_run += 1
            if silence_run >= silence_frames_needed:
                break

    audio = np.concatenate(frames, axis=0)
    return _normalize_volume(audio)


# 목소리가 작거나 마이크 볼륨이 낮아도 인식이 잘 되도록, 녹음된 소리를 증폭해서 최대
# 진폭이 목표치(전체 스케일의 70%)에 가깝도록 맞춘다.
_TARGET_PEAK_RATIO = 0.7
# 사실상 무음(주변 잡음 수준)인 녹음은 증폭해봐야 잡음만 커지고 오인식만 늘어나므로 건너뛴다.
_SILENCE_PEAK_THRESHOLD = 50
# 무음에 가까운 아주 작은 신호를 과하게 증폭해 잡음을 말소리로 오인하지 않도록 배율 상한을 둔다.
_MAX_GAIN = 10.0


def _normalize_volume(audio):
    peak = int(np.abs(audio).max())
    if peak < _SILENCE_PEAK_THRESHOLD:
        return audio
    gain = min((32767 * _TARGET_PEAK_RATIO) / peak, _MAX_GAIN)
    return np.clip(audio.astype(np.float32) * gain, -32768, 32767).astype(np.int16)


def _transcribe(model, audio, hotwords=None):
    float_audio = audio.flatten().astype(np.float32) / 32768.0
    segments, _ = model.transcribe(float_audio, language="ko", hotwords=hotwords)
    return "".join(seg.text for seg in segments).strip()


def _edit_distance(a, b):
    if len(a) < len(b):
        a, b = b, a
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


_PUNCTUATION_PATTERN = re.compile(r"[\s.,!?~…·\"'　]")


def sounds_like_wake_word(text):
    """인식된 텍스트 맨 앞부분이 '커리마'와 비슷하게 들리는지 확인한다."""
    normalized = _PUNCTUATION_PATTERN.sub("", text)
    if not normalized:
        return False
    candidate = normalized[: len(WAKE_WORD) + 1]
    return _edit_distance(candidate, WAKE_WORD) <= MAX_EDIT_DISTANCE


def _sounds_like_yes(text):
    """확인 질문에 대한 대답이 긍정('네'/'응'/'그래' 등)으로 시작하는지 확인한다.
    애매하면(빈 대답, 부정, 인식 실패 등) 안전하게 취소 쪽으로 판정한다."""
    normalized = _PUNCTUATION_PATTERN.sub("", text)
    return any(normalized.startswith(word) for word in _AFFIRMATIVE_WORDS)


def _beep():
    winsound.Beep(880, 150)


def _speech_friendly(text):
    """마크다운 기호를 지운다. Gemini 응답을 그대로 읽으면 '별표 별표'처럼 이상하게 들린다."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"[*`_]", "", text)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^[-•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*\n+\s*", ". ", text)
    text = re.sub(r"\.\s*\.", ".", text)
    return text.strip()


# Windows 토스트 알림은 평상시엔 몇 줄만 보이고 마우스를 올려야 전체가 펼쳐져서, 길게
# 보내면 잘린 채로 보인다. 화면에는 짧은 요약만 띄우고, 자세한 내용은 음성으로 전달한다.
_NOTIFICATION_PREVIEW_CHARS = 60


def _notification_preview(text):
    if len(text) <= _NOTIFICATION_PREVIEW_CHARS:
        return text
    return text[:_NOTIFICATION_PREVIEW_CHARS].rstrip() + "… (음성으로 이어서 말씀드릴게요)"


def _function_result(step, result):
    return {
        "type": "function_result",
        "name": step.name,
        "call_id": step.id,
        "result": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
    }


def _run_confirmed_tool(step):
    """음성으로 확인을 이미 받은 위험한 도구를 실행한다.

    kurima_app.execute_tool_call은 CONFIRM_MESSAGES에 등록된 도구를 다시 만나면
    터미널 input()으로 y/n을 받으려 하는데, 이 스레드에는 그런 터미널이 없어서 그대로
    부르면 응답 없이 멈춘다. 그래서 확인이 끝난 뒤에는 도구 함수를 직접 호출한다.
    """
    func = tools.FUNCTION_MAP[step.name]
    result = func(**step.arguments)
    return _function_result(step, result)


def _confirm_by_voice(message, notify, speak):
    """위험한 동작을 실행하기 전에 음성으로 확인받는다. 삐 소리 후 대답을 듣고,
    긍정으로 들리지 않으면(애매한 경우 포함) 안전하게 취소한다."""
    prompt = f"{message} 진행할까요? 네, 또는 아니요라고 답해주세요."
    notify("커리마", _notification_preview(prompt))
    speak(prompt)
    _beep()
    answer_audio = _record_until_silence(CONFIRM_ANSWER_SECONDS)
    answer_text = _transcribe(_get_command_model(), answer_audio)
    return _sounds_like_yes(answer_text)


def handle_command(text, notify, speak):
    """음성으로 들어온 명령 한 문장을 커리마 도구 파이프라인으로 처리하고 결과를 알림+음성으로 돌려준다.

    확인이 필요한 위험한 도구(app_close/file_delete 등)를 부르려고 하면, 실행 전에
    음성으로 "진행할까요?"라고 되묻고 긍정 대답이 돌아왔을 때만 실행한다.
    """
    notify("커리마", "생각 중...")
    interaction = kurima_app.create_interaction(text, None)

    while True:
        call_steps = [s for s in interaction.steps if s.type == "function_call"]
        if not call_steps:
            break

        results = []
        for step in call_steps:
            confirm_message = tools.CONFIRM_MESSAGES.get(step.name)
            if confirm_message is None:
                results.append(kurima_app.execute_tool_call(step))
            elif _confirm_by_voice(confirm_message(step.arguments), notify, speak):
                results.append(_run_confirmed_tool(step))
            else:
                results.append(_function_result(step, {"message": "사용자가 취소해서 실행하지 않았습니다."}))
        interaction = kurima_app.create_interaction(results, interaction.id)

    answer = _speech_friendly(interaction.output_text or "답을 만들지 못했어요.")
    notify("커리마", _notification_preview(answer))
    speak(answer)


def run_loop(stop_event, enabled_event, notify, speak):
    """별도 스레드에서 짧은 구간을 계속 녹음해 웨이크워드를 확인하고, 들리면 명령을 받는다.

    enabled_event가 꺼져 있으면(트레이 메뉴에서 음성 인식을 껐을 때) 녹음을 건너뛰고 대기만 한다.
    """
    wake_model = _get_wake_model()
    while not stop_event.is_set():
        if not enabled_event.is_set():
            stop_event.wait(1.0)
            continue
        try:
            chunk = _record(WAKE_CHUNK_SECONDS)
            heard = _transcribe(wake_model, chunk, hotwords=WAKE_WORD)
            if sounds_like_wake_word(heard):
                _beep()
                command_audio = _record_until_silence(COMMAND_SECONDS)
                command_text = _transcribe(_get_command_model(), command_audio)
                if command_text:
                    handle_command(command_text, notify, speak)
        except Exception:
            pass  # 인식 한 번 실패해도 계속 듣고 있어야 한다.
