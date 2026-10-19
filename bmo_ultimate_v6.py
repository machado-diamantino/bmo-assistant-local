#!/usr/bin/env python3
"""
bmo_ultimate_v6.py — BMO AI Agent Ultimate V6 (Édition V6.3 Perfect Vision)
Optimisé pour Raspberry Pi 5 — Correction de la taille d'image et du bug de langue
"""

import asyncio
import base64
import datetime
import json
import os
import threading
import time
import wave

import cv2
import numpy as np
import ollama
import pygame
import requests
from piper import PiperVoice
from piper.config import SynthesisConfig

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════
IP_CAMERA        = "172.16.83.102"
URL_VIDEO        = f"http://{IP_CAMERA}:4747/video"
# Petit modèle conversationnel : rapide sur Raspberry Pi et bon en français.
OLLAMA_MODEL     = "qwen3:0.6b"
VISION_MODEL     = "moondream"            # Modèle vision
MODEL_OPTIONS    = {"num_predict": 60, "num_ctx": 2048, "temperature": 0.5}
FPS              = 60
ANIM_FPS_IDLE    = 4
ANIM_FPS_TALK    = 10
ANIM_FPS_THINK   = 3
TRANSCRIPT_LINES = 3

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json")
MEMORY_MAX_MESSAGES = 12       # Six échanges conservés sur le disque.
CONTEXT_MESSAGES = 4           # Deux échanges seulement envoyés au modèle.
PIPER_MODEL  = os.path.join(BASE_DIR, "voices", "fr_FR-siwis-medium.onnx")
PIPER_CONFIG = f"{PIPER_MODEL}.json"
TMP_AUDIO    = "/tmp/bmo_tts.wav"
IMG_IDLE   = os.path.join(BASE_DIR, "images", "idle")
IMG_TALK   = os.path.join(BASE_DIR, "images", "talk")
IMG_THINK  = os.path.join(BASE_DIR, "images", "think")
SYSTEM_PROMPT = (
    "Tu es BMO, l'assistant personnel amical de Diamantino. "
    "Tu réponds exclusivement en français, avec un ton chaleureux, simple et naturel. "
    "Tu aides à discuter et à répondre à des questions du quotidien : culture générale, "
    "explications simples, idées, organisation, informatique de base et conseils pratiques. "
    "Réponds en une à trois phrases, sauf si Diamantino demande explicitement plus de détails. "
    "Si une question est ambiguë, pose une seule question courte pour clarifier. "
    "N'invente jamais une information : dis clairement quand tu ne sais pas. "
    "Pour la santé, le droit ou l'argent, donne seulement des informations générales et "
    "recommande un professionnel lorsque c'est nécessaire. "
    "Ne prétends pas pouvoir faire une action que tu ne peux pas réellement effectuer."
)

C_TEAL   = ( 40, 200, 200)
C_DARK   = ( 10,  10,  10)
C_WHITE  = (255, 255, 255)
C_GREEN  = (  0, 255, 100)
C_YELLOW = (255, 230,   0)
C_BLUE   = ( 80, 140, 255)
C_RED    = (255,  80,  80)
C_TRANS  = ( 10,  10,  40, 210)

class State:
    IDLE, THINK, TALK = "idle", "think", "talk"

g_state          = State.IDLE
g_transcript     = ""
g_user_input     = ""
g_camera_active  = False
g_executing      = False
g_conv_history   = []
g_piper_voice    = None
g_voice_channel  = None
g_active_task    = None

QUICK_ACTIONS = [
    ("HEURE", "Quelle heure est-il ?"),
    ("CAMERA", "Active la caméra"),
    ("EXPLIQUE", "Explique-moi quelque chose simplement."),
    ("MEMOIRE", "Que sais-tu de moi ?"),
    ("STOP", "__stop__"),
]

def load_memory() -> list[dict[str, str]]:
    """Charge les derniers messages valides, y compris l'ancien format de mémoire."""
    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as memory_file:
            data = json.load(memory_file)
        messages = data.get("messages", []) if isinstance(data, dict) else data
        valid_messages = [
            {"role": message["role"], "content": message["content"]}
            for message in messages
            if isinstance(message, dict)
            and message.get("role") in {"user", "assistant"}
            and isinstance(message.get("content"), str)
        ]
        return valid_messages[-MEMORY_MAX_MESSAGES:]
    except (OSError, ValueError, TypeError):
        return []

def save_memory(messages: list[dict[str, str]]) -> None:
    """Sauvegarde la mémoire localement sans risque de fichier partiellement écrit."""
    memory_data = {"messages": messages[-MEMORY_MAX_MESSAGES:]}
    temporary_file = f"{MEMORY_FILE}.tmp"
    try:
        with open(temporary_file, "w", encoding="utf-8") as memory_file:
            json.dump(memory_data, memory_file, ensure_ascii=False, indent=2)
        os.replace(temporary_file, MEMORY_FILE)
    except OSError:
        try:
            os.unlink(temporary_file)
        except OSError:
            pass

# ═══════════════════════════════════════════════════════════════════════════
# ANIMATION MANAGER
# ═══════════════════════════════════════════════════════════════════════════
class AnimationManager:
    def __init__(self, directory: str, anim_fps: int = 8):
        self.frames = []
        self.anim_fps = anim_fps
        self.idx      = 0
        self._last    = time.perf_counter()
        self._load(directory)

    def _load(self, directory: str) -> None:
        if not os.path.isdir(directory): return
        files = sorted(f for f in os.listdir(directory) if f.lower().endswith(".png"))
        for f in files:
            try:
                surf = pygame.image.load(os.path.join(directory, f)).convert()
                self.frames.append(surf)
            except Exception: pass

    def update(self) -> None:
        if not self.frames: return
        now = time.perf_counter()
        if now - self._last >= 1.0 / self.anim_fps:
            self.idx   = (self.idx + 1) % len(self.frames)
            self._last = now

    @property
    def current(self) -> pygame.Surface | None:
        return self.frames[self.idx] if self.frames else None

# ═══════════════════════════════════════════════════════════════════════════
# VISION MANAGER (RÉSOLUTION OPTIMALE 480P)
# ═══════════════════════════════════════════════════════════════════════════
class VisionManager:
    def __init__(self, url: str):
        self.url        = url
        self._cap       = None
        self._lock      = threading.Lock()
        self._rgb_small = None
        self._raw_frame = None
        self.running    = False
        self._thread    = None

    def start(self) -> None:
        if self.running: return
        self._cap   = cv2.VideoCapture(self.url)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.running = False
        if self._cap:
            self._cap.release()
            self._cap = None

    def get_surface(self) -> pygame.Surface | None:
        with self._lock: arr = self._rgb_small
        return pygame.surfarray.make_surface(np.transpose(arr, (1, 0, 2))) if arr is not None else None

    def get_clean_b64_jpeg(self) -> str | None:
        """ Extrait une image en 640x480 pour une détection ultra-précise sans bug """
        if not self._cap or not self._cap.isOpened(): return None
        for _ in range(4): self._cap.grab()
        ret, frame = self._cap.retrieve()
        if not ret or frame is None:
            with self._lock: frame = self._raw_frame
        if frame is None: return None

        # AJUSTEMENT : 640x480 donne assez de détails à Moondream pour ne pas buguer en anglais
        frame_clean = cv2.resize(frame, (640, 480))
        _, buf = cv2.imencode(".jpg", frame_clean, [cv2.IMWRITE_JPEG_QUALITY, 75])
        return base64.b64encode(buf.tobytes()).decode()

    def _read_loop(self) -> None:
        while self.running:
            if not (self._cap and self._cap.isOpened()):
                time.sleep(0.2)
                continue
            ret, frame = self._cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            small = cv2.resize(rgb, (320, 180))
            with self._lock:
                self._rgb_small = small
                self._raw_frame = frame
            time.sleep(0.02)

vision_mgr: VisionManager | None = None

# ═══════════════════════════════════════════════════════════════════════════
# AUDIO & OLLAMA
# ═══════════════════════════════════════════════════════════════════════════
async def speak(text: str) -> None:
    """Fait parler BMO et publie simultanément la phrase dans la transcription."""
    global g_state, g_transcript, g_voice_channel
    g_state    = State.TALK
    g_transcript = f"BMO : {text}"
    try:
        # Piper reste chargé en mémoire : aucune requête cloud ni redémarrage.
        await asyncio.to_thread(synthesize_with_piper, text)
        snd = pygame.mixer.Sound(TMP_AUDIO)
        g_voice_channel = snd.play()
        while g_voice_channel and g_voice_channel.get_busy():
            await asyncio.sleep(0.05)
    except Exception: pass
    finally:
        g_voice_channel = None
        g_state = State.IDLE

def stop_bmo() -> None:
    """Interrompt immédiatement la voix et la tâche de réponse en cours."""
    global g_active_task, g_executing, g_state, g_transcript, g_voice_channel
    if g_voice_channel:
        g_voice_channel.stop()
    pygame.mixer.stop()
    if g_active_task and not g_active_task.done():
        g_active_task.cancel()
    g_active_task = None
    g_voice_channel = None
    g_executing = False
    g_state = State.IDLE
    g_transcript = "BMO : Arrêté."

def start_command(cmd: str) -> None:
    """Lance une demande via le clavier ou un bouton, sauf si BMO travaille déjà."""
    global g_active_task, g_user_input
    if cmd == "__stop__":
        stop_bmo()
        return
    if g_active_task and not g_active_task.done():
        return
    g_user_input = ""
    g_active_task = asyncio.create_task(execute(cmd))

def load_piper() -> None:
    global g_piper_voice
    g_piper_voice = PiperVoice.load(PIPER_MODEL, config_path=PIPER_CONFIG)

def synthesize_with_piper(text: str) -> None:
    if g_piper_voice is None:
        raise RuntimeError("La voix Piper n'est pas chargée.")
    with wave.open(TMP_AUDIO, "wb") as wav_file:
        g_piper_voice.synthesize_wav(
            text,
            wav_file,
            syn_config=SynthesisConfig(length_scale=0.92),
        )

async def warm_up_model() -> None:
    """Charge Qwen au démarrage pour éviter la lenteur de la première question."""
    try:
        client = ollama.AsyncClient()
        await client.generate(
            model=OLLAMA_MODEL,
            prompt="Bonjour",
            think=False,
            options={"num_predict": 1, "num_ctx": 2048},
            keep_alive=-1,
        )
    except Exception:
        # BMO reste utilisable : l'erreur détaillée apparaîtra à la première question.
        pass

async def stream_reply(prompt: str) -> str:
    global g_transcript, g_state, g_conv_history
    g_state, g_transcript = State.THINK, "BMO : "
    user_msg = {"role": "user", "content": prompt}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *g_conv_history[-CONTEXT_MESSAGES:],
        user_msg,
    ]
    full_reply = ""
    try:
        client = ollama.AsyncClient()
        async for chunk in await client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            stream=True,
            think=False,
            options=MODEL_OPTIONS,
            keep_alive=-1,
        ):
            token = chunk["message"]["content"]
            full_reply += token
            # Le bloc de transcription se remplit au rythme de la réponse IA.
            g_transcript += token
            await asyncio.sleep(0)
    except Exception as e:
        full_reply = f"Erreur : {e}"
        g_transcript = f"BMO : {full_reply}"
    g_conv_history.append(user_msg)
    g_conv_history.append({"role": "assistant", "content": full_reply})
    g_conv_history = g_conv_history[-MEMORY_MAX_MESSAGES:]
    save_memory(g_conv_history)
    return full_reply

# ═══════════════════════════════════════════════════════════════════════════
# EXECUTE COMMANDS
# ═══════════════════════════════════════════════════════════════════════════
async def execute(cmd: str) -> None:
    global g_executing, g_camera_active, vision_mgr, g_state, g_transcript
    if g_executing: return
    g_executing = True

    try:
        c = cmd.lower().strip()

        if "heure" in c:
            await speak(f"Il est {datetime.datetime.now().strftime('%H:%M')}.")

        elif any(k in c for k in ("ferme", "coupe", "éteins")) and any(k in c for k in ("yeux", "caméra", "camera")):
            if vision_mgr: vision_mgr.stop()
            g_camera_active, g_state = False, State.IDLE
            await speak("Caméra coupée.")

        # ANALYSE DE LA VISION CORRIGÉE
        elif any(k in c for k in ("active", "regarde", "vois", "vision", "analyse", "couleur", "t-shirt", "tee-shirt", "pull")):
            if not g_camera_active:
                g_camera_active = True
                vision_mgr = VisionManager(URL_VIDEO)
                vision_mgr.start()
                await speak("J'allume ma caméra DroidCam. Repose-moi ta question.")
                return

            g_state = State.THINK
            g_transcript = "[BMO analyse ton image...]"

            b64 = vision_mgr.get_clean_b64_jpeg() if vision_mgr else None
            if not b64:
                g_state = State.IDLE
                await speak("Je ne reçois pas d'image.")
                return

            try:
                # ÉJECTE LE MODÈLE TEXTE POUR DONNER TOUTE LA RAM À MOONDREAM
                requests.post("http://localhost:11434/api/chat", json={"model": OLLAMA_MODEL, "messages": [], "keep_alive": 0}, timeout=2)

                client = ollama.AsyncClient()

                # Instruction claire en FRANÇAIS, interdiction absolue de l'anglais
                prompt_secure = "Décris en une courte phrase en français la couleur du t-shirt ou vêtement de la personne au centre."

                resp = await client.generate(
                    model=VISION_MODEL,
                    prompt=prompt_secure,
                    images=[b64],
                    options={
                        "temperature": 0.2,
                        "num_predict": 30   # Laisse assez de place pour une phrase en français propre
                    }
                )

                reponse_ia = resp["response"].strip()
                g_transcript = f"BMO : {reponse_ia}"
                await speak(reponse_ia)

            except Exception as e:
                g_state = State.IDLE
                g_transcript = f"[Erreur IA : {e}]"
                await speak("Désolé, j'ai eu du mal à analyser l'image.")

        else:
            reply = await stream_reply(cmd)
            await speak(reply)

    except Exception: g_state = State.IDLE
    finally: g_executing = False

# ═══════════════════════════════════════════════════════════════════════════
# GRAPHICS & INTERFACE
# ═══════════════════════════════════════════════════════════════════════════
def wrap_text(text: str, font: pygame.font.Font, max_w: int) -> list[str]:
    words, lines, line = text.split(), [], ""
    for w in words:
        candidate = f"{line} {w}".strip()
        if font.size(candidate)[0] <= max_w: line = candidate
        else:
            if line: lines.append(line)
            line = w
    if line: lines.append(line)
    return lines or [""]

def quick_action_rects(W: int, H: int) -> list[tuple[pygame.Rect, str]]:
    """Construit les boutons visibles juste au-dessus de la zone de saisie."""
    gap, margin, height = 8, 15, 38
    width = (W - (2 * margin) - (gap * (len(QUICK_ACTIONS) - 1))) // len(QUICK_ACTIONS)
    y = H - 116
    return [
        (pygame.Rect(margin + index * (width + gap), y, width, height), command)
        for index, (_, command) in enumerate(QUICK_ACTIONS)
    ]

def draw_frame(screen: pygame.Surface, anims: dict, fonts: dict, W: int, H: int) -> None:
    screen.fill(C_TEAL)
    anim = anims.get(g_state) or anims[State.IDLE]
    anim.update()
    frame_surf = anim.current
    if frame_surf:
        sw, sh  = frame_surf.get_size()
        scale   = min((H * 0.68) / sh, (W * 0.72) / sw)
        nw, nh  = int(sw * scale), int(sh * scale)
        scaled  = pygame.transform.smoothscale(frame_surf, (nw, nh))
        screen.blit(scaled, ((W - nw) // 2, (H - nh) // 2 - 55))

    if g_camera_active and vision_mgr:
        cam_surf = vision_mgr.get_surface()
        if cam_surf:
            cam_x, cam_y = W - 334, 10
            pygame.draw.rect(screen, C_WHITE, (cam_x - 2, cam_y - 2, 326, 186), 3, border_radius=8)
            screen.blit(cam_surf, (cam_x, cam_y))

    if g_transcript:
        box_x, box_w  = 15, W - 30
        box_h  = TRANSCRIPT_LINES * 34 + 44
        box_y  = H - 275
        overlay = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        overlay.fill(C_TRANS)
        screen.blit(overlay, (box_x, box_y))
        pygame.draw.rect(screen, C_BLUE, (box_x, box_y, box_w, box_h), 2, border_radius=8)
        title = fonts["xs"].render("● TRANSCRIPTION DE BMO", True, C_GREEN)
        screen.blit(title, (box_x + 10, box_y + 7))
        lines = wrap_text(g_transcript, fonts["sm"], box_w - 20)
        for i, ln in enumerate(lines[-TRANSCRIPT_LINES:]):
            surf = fonts["sm"].render(ln, True, C_WHITE)
            screen.blit(surf, (box_x + 10, box_y + 34 + i * 34))

    for index, (rect, _) in enumerate(quick_action_rects(W, H)):
        label = QUICK_ACTIONS[index][0]
        color = C_RED if label == "STOP" else C_BLUE
        pygame.draw.rect(screen, C_DARK, rect, border_radius=8)
        pygame.draw.rect(screen, color, rect, 2, border_radius=8)
        label_surf = fonts["xs"].render(label, True, color)
        screen.blit(label_surf, label_surf.get_rect(center=rect.center))

    inp_y   = H - 65
    inp_rect = pygame.Rect(15, inp_y, W - 30, 54)
    pygame.draw.rect(screen, C_DARK, inp_rect, border_radius=10)
    pygame.draw.rect(screen, C_GREEN, inp_rect, 2, border_radius=10)
    cursor  = "|" if int(time.time() * 2) % 2 == 0 else " "
    display = f"▶  {g_user_input}{cursor}"
    while fonts["md"].size(display)[0] > inp_rect.width - 20: display = "▶  …" + display[5:]
    txt_surf = fonts["md"].render(display, True, C_GREEN)
    screen.blit(txt_surf, (inp_rect.x + 12, inp_rect.y + 12))

    state_col = {State.IDLE: C_GREEN, State.THINK: C_YELLOW, State.TALK: C_BLUE}
    slbl = fonts["xs"].render(f"[{g_state.upper()}]", True, state_col.get(g_state, C_WHITE))
    screen.blit(slbl, (12, 10))
    if g_camera_active:
        clbl = fonts["xs"].render("● VISION LIVE", True, C_RED)
        screen.blit(clbl, (12, 34))
    pygame.display.flip()

async def main() -> None:
    global g_user_input, g_conv_history
    pygame.init()
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    pygame.mouse.set_visible(True)
    g_conv_history = load_memory()

    info, W, H = pygame.display.Info(), pygame.display.Info().current_w, pygame.display.Info().current_h
    screen    = pygame.display.set_mode((W, H), pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.HWSURFACE)
    clock     = pygame.time.Clock()

    fonts = {
        "xs": pygame.font.SysFont("monospace", max(14, H // 45)),
        "sm": pygame.font.SysFont("monospace", max(19, H // 32)),
        "md": pygame.font.SysFont("monospace", max(23, H // 24), bold=True),
    }
    anims = {
        State.IDLE:  AnimationManager(IMG_IDLE,  ANIM_FPS_IDLE),
        State.TALK:  AnimationManager(IMG_TALK,  ANIM_FPS_TALK),
        State.THINK: AnimationManager(IMG_THINK, ANIM_FPS_THINK),
    }

    await asyncio.to_thread(load_piper)
    await warm_up_model()
    await speak("BMO prêt avec vision ajustée.")

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: running = False
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for rect, command in quick_action_rects(W, H):
                    if rect.collidepoint(event.pos):
                        start_command(command)
                        break
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE: running = False
                elif event.key == pygame.K_RETURN:
                    cmd = g_user_input.strip()
                    if cmd:
                        if any(word in cmd.lower() for word in ("stop", "tais-toi", "arrête")):
                            stop_bmo()
                        else:
                            start_command(cmd)
                elif event.key == pygame.K_BACKSPACE: g_user_input = g_user_input[:-1]
                elif event.unicode and event.unicode.isprintable(): g_user_input += event.unicode

        draw_frame(screen, anims, fonts, W, H)
        clock.tick(FPS)
        await asyncio.sleep(0)

    if vision_mgr: vision_mgr.stop()
    pygame.quit()

if __name__ == "__main__":
    asyncio.run(main())