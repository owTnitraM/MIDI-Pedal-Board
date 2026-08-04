# midi_pedals_definitivo.py
# Windows 11 + loopMIDI expected (TecladoVirtual*, PyMerged* already created)
# Dependências: mido, python-rtmidi, pynput

import sys
import time
import mido
from mido import Message                  
from pynput import keyboard

# -------- CONFIGURÁVEIS --------
USB_NAME_CONTAINS = 'usb2.0-midi'   # substring (case-insensitive) para detectar sua entrada USB
TECLADO_OUTPUT_CONTAINS = 'tecladovirtual'  # porta para onde será encaminhado o MIDI cru
MERGE_OUTPUT_CONTAINS = 'pymerged'          # porta onde sairá o MIDI processado

# -------- ESTADO --------
toggle_mode = False   # False = HOLD (default), True = TOGGLE
mod_down = False      # -1 oitava (Ctrl)
mod_up = False        # +1 oitava (Alt)
sustain = False       # sustain (Space) - always HOLD
active_notes = {}     # mapa original_note -> (sent_note, velocity)

# -------- UTIL PARA PORTAS --------
def find_input_by_contains(substr):
    s = substr.lower()
    for name in mido.get_input_names():
        if s in name.lower():
            return name
    return None

def find_output_by_contains(substr):
    s = substr.lower()
    for name in mido.get_output_names():
        if s in name.lower():
            return name
    return None

# -------- LÓGICA DE NOTAS --------
def calculate_note_once(note, mod_down_flag, mod_up_flag):
    """Calcula nota no momento do envio. Não remapeia notas já ativas."""
    if mod_down_flag and not mod_up_flag:
        return max(0, note - 12)
    if mod_up_flag and not mod_down_flag:
        return min(127, note + 12)
    return note

def send_note_on(orig_note, velocity, out_merge):
    """Envia note_on para PyMerged; ignora se orig_note já ativa."""
    if orig_note in active_notes:
        # já enviamos essa nota (ignore retriggers como nos exemplos)
        return
    sent = calculate_note_once(orig_note, mod_down, mod_up)
    out_merge.send(Message('note_on', note=sent, velocity=velocity))
    active_notes[orig_note] = (sent, velocity)
    print(f"[SEND ON] orig={orig_note} -> sent={sent} vel={velocity}")

def send_note_off(orig_note, out_merge):
    """Envia note_off de acordo com a nota que foi enviada anteriormente."""
    pair = active_notes.pop(orig_note, None)
    if pair:
        sent_note, _ = pair
        out_merge.send(Message('note_off', note=sent_note, velocity=0))
        print(f"[SEND OFF] orig={orig_note} -> sent={sent_note}")

def release_all(out_merge):
    """Solta tudo em PyMerged e envia sustain off se estiver ativo."""
    for orig, (sent, _) in list(active_notes.items()):
        out_merge.send(Message('note_off', note=sent, velocity=0))
        print(f"[RELEASE] orig={orig} sent={sent}")
    active_notes.clear()
    if sustain:
        out_merge.send(Message('control_change', control=64, value=0))
        print("[RELEASE] sustain OFF")

# -------- TECLADO (pynput) HANDLERS --------
def make_keyboard_handlers(in_usb, out_teclado, out_merge):
    """
    Retorna on_press, on_release — closures que manipulam estados globais.
    Behavior:
     - Space: sustain (HOLD)
     - Ctrl: octave -1 (HOLD or TOGGLE based on toggle_mode)
     - Alt: octave +1 (HOLD or TOGGLE based on toggle_mode)
     - Enter: switch HOLD <-> TOGGLE for octave pedals
     - Esc: exit cleanly
    """
    def on_press(key):
        global mod_down, mod_up, sustain, toggle_mode
        try:
            # Toggle mode switch (Enter)
            if key == keyboard.Key.enter:
                toggle_mode = not toggle_mode
                mode = "TOGGLE" if toggle_mode else "HOLD"
                print(f"[KEY] modo de modulação: {mode}")
                return

            # ESC -> exit
            if key == keyboard.Key.esc:
                print("[KEY] ESC pressed, exiting...")
                release_all(out_merge)
                try:
                    in_usb.close()
                except: pass
                try:
                    out_teclado.close()
                except: pass
                try:
                    out_merge.close()
                except: pass
                raise SystemExit

            # Space -> sustain ON (hold)
            if key == keyboard.Key.space:
                if not sustain:
                    sustain = True
                    out_merge.send(Message('control_change', control=64, value=127))
                    print("[KEY] sustain ON (space)")

            # Ctrl handling (either hold or toggle)
            if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                if toggle_mode:
                    mod_down = not mod_down
                    print(f"[KEY] Ctrl (toggle) -> mod_down = {mod_down}")
                else:
                    if not mod_down:
                        mod_down = True
                        print("[KEY] Ctrl (hold) -> mod_down ON")
                # NOTE: we DO NOT remap active notes; only new notes will use this mod

            # Alt handling
            if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                if toggle_mode:
                    mod_up = not mod_up
                    print(f"[KEY] Alt (toggle) -> mod_up = {mod_up}")
                else:
                    if not mod_up:
                        mod_up = True
                        print("[KEY] Alt (hold) -> mod_up ON")
        except SystemExit:
            raise
        except Exception as e:
            print("Erro on_press:", e)

    def on_release(key):
        global mod_down, mod_up, sustain, toggle_mode
        try:
            # Space released -> sustain OFF
            if key == keyboard.Key.space:
                if sustain:
                    sustain = False
                    out_merge.send(Message('control_change', control=64, value=0))
                    print("[KEY] sustain OFF (space released)")

            # If we're in HOLD mode, releasing Ctrl/Alt turns off mod
            if not toggle_mode:
                if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                    if mod_down:
                        mod_down = False
                        print("[KEY] Ctrl released -> mod_down OFF")
                if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
                    if mod_up:
                        mod_up = False
                        print("[KEY] Alt released -> mod_up OFF")
            # In TOGGLE mode, releases do nothing (state changed on press)
        except Exception as e:
            print("Erro on_release:", e)

    return on_press, on_release

# -------- MAIN --------
def main():
    print("Procurando portas MIDI...")
    in_name = find_input_by_contains(USB_NAME_CONTAINS)
    out_tecl_name = find_output_by_contains(TECLADO_OUTPUT_CONTAINS)
    out_merge_name = find_output_by_contains(MERGE_OUTPUT_CONTAINS)

    if not in_name:
        print(f"ERRO: não achei entrada contendo '{USB_NAME_CONTAINS}'.")
        print("Inputs disponíveis:")
        for n in mido.get_input_names():
            print("  ", n)
        sys.exit(1)
    if not out_tecl_name or not out_merge_name:
        print("ERRO: não achei as portas de saída esperadas (crie via loopMIDI):")
        for n in mido.get_output_names():
            print("  ", n)
        sys.exit(1)

    print(f"Usando INPUT: {in_name}")
    print(f"Usando TECLADO virtual (raw): {out_tecl_name}")
    print(f"Usando MERGE (processado): {out_merge_name}")

    in_usb = mido.open_input(in_name)
    out_teclado = mido.open_output(out_tecl_name)
    out_merge = mido.open_output(out_merge_name)

    print("\nRodando. Teclas: Space = sustain (hold). Ctrl = -1 oitava. Alt = +1 oitava.")
    print("Enter alterna HOLD <-> TOGGLE para pedais de oitava. ESC para sair.\n")

    on_press, on_release = make_keyboard_handlers(in_usb, out_teclado, out_merge)
    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()

    try:
        while True:
            for msg in in_usb.iter_pending():
                if msg.type == 'note_on' and msg.velocity > 0:
                    # só manda o raw se não houver modulação ativa
                    if not mod_down and not mod_up:
                        out_teclado.send(msg)
                    send_note_on(msg.note, msg.velocity, out_merge)

                elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                    if not mod_down and not mod_up:
                        out_teclado.send(msg)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  
                    send_note_off(msg.note, out_merge)

                else:
                    # CC, program change, pitchwheel etc. — encaminha para os dois sempre
                    out_teclado.send(msg)
                    out_merge.send(msg)

            time.sleep(0.002)
    except SystemExit:
        print("Encerrando via SystemExit.")
    except KeyboardInterrupt:
        print("Encerrado por Ctrl+C.")
    finally:
        release_all(out_merge)
        try:
            listener.stop()
        except: pass
        try:
            in_usb.close()
            out_teclado.close()
            out_merge.close()
        except: pass
        print("Finalizado.")

if __name__ == '__main__':
    main()