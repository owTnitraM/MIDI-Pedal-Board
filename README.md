# MIDI Pedals — Oitava + Sustain via teclado

Script Python que lê um controlador MIDI USB e usa o **teclado do PC como "pedais"** para aplicar efeitos como: deslocar oitavas e aplicar sustain, encaminhando o resultado para portas MIDI virtuais (via loopMIDI) para uso em outros programas (DAW, VST host, etc).

## Requisitos

- **Windows 11**
- [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) com duas portas virtuais já criadas:
  - uma para o MIDI "cru" (ex: `TecladoVirtual`)
  - uma para o MIDI processado (ex: `PyMerged`)
- Python 3 com as libs:
  ```bash
  pip install mido python-rtmidi pynput
  ```

## Como rodar

```bash
python midi_pedals_definitivo.py
```

O script procura automaticamente:
1. sua entrada MIDI USB,
2. a porta virtual de saída "crua",
3. a porta virtual de saída "processada",

comparando os nomes das portas disponíveis com os textos configurados nas variáveis (veja abaixo). Se não achar alguma, ele lista as portas disponíveis no terminal para você conferir o nome exato.

## Teclas ("pedais")

| Tecla | Ação |
|---|---|
| **Espaço** | Sustain (CC64) — sempre no modo *hold* (segura = ligado, solta = desligado) |
| **Ctrl** (esq. ou dir.) | Transpõe **-1 oitava** as próximas notas tocadas |
| **Alt** (esq. ou dir.) | Transpõe **+1 oitava** as próximas notas tocadas |
| **Enter** | Alterna o modo do Ctrl/Alt entre **HOLD** (segurar) e **TOGGLE** (aperta uma vez liga, aperta de novo desliga) |
| **Esc** | Encerra o programa, soltando todas as notas e sustain pendentes |

**Importante:** o deslocamento de oitava só vale para notas **novas**. Uma nota que já está soando não muda de altura no meio do caminho se você apertar Ctrl/Alt depois — isso evita "pulos" estranhos de nota no meio do som.

## O que sai em cada porta

- **Porta "Teclado virtual" (crua):** recebe o MIDI original, nota por nota, **só quando nenhum modificador de oitava está ativo**. Serve como um espelho do teclado físico sem processamento.
- **Porta "Merge" (processada):** sempre recebe o resultado final — com oitava deslocada quando aplicável, sustain (CC64) e qualquer outra mensagem (CC, pitch bend, program change etc, que são sempre repassadas para as duas portas).

## Variáveis para adaptar ao seu setup

No topo do arquivo:

```python
USB_NAME_CONTAINS = 'usb2.0-midi'      # trecho do nome da SUA entrada MIDI USB
TECLADO_OUTPUT_CONTAINS = 'tecladovirtual'  # trecho do nome da porta virtual "crua"
MERGE_OUTPUT_CONTAINS = 'pymerged'          # trecho do nome da porta virtual "processada"
```

A busca é por **substring, sem diferenciar maiúsculas/minúsculas** — não precisa ser o nome exato, só um pedaço único que identifique a porta certa.

**Como descobrir o nome certo da sua porta:** rode o script uma vez. Se ele não achar alguma porta, vai imprimir a lista completa de entradas/saídas MIDI disponíveis no Windows. Copie o trecho relevante do nome que aparecer lá e cole na variável correspondente.

Outros pontos fáceis de mexer:

- **Faixa de transposição:** hoje é fixo em ±12 semitons (1 oitava). Para mudar, edite `calculate_note_once()`:
  ```python
  return max(0, note - 12)   # troque o 12 por outro valor
  ```
- **Controle de sustain:** usa CC64 (padrão MIDI de sustain pedal). Para usar outro CC, troque o `control=64` nas chamadas de `control_change`.
- **Outras teclas:** os handlers ficam em `make_keyboard_handlers()`. Dá pra trocar `keyboard.Key.space`, `.ctrl_l/r`, `.alt_l/r` por qualquer outra tecla do `pynput.keyboard`.

## Observações

- O terminal fica imprimindo cada nota enviada/solta (`[SEND ON]`, `[SEND OFF]`, etc) — útil pra debugar, mas pode virar bastante texto se você tocar rápido.
- Fechar com **Esc** é o jeito "limpo" de sair (solta notas e sustain pendurados). `Ctrl+C` também funciona como saída de emergência.
- Este programa foi feito para uso pessoal e está adaptado para meu caso de uso, sinta-se à vontade para o reconfigurar, mudar keybinds e portas, ou até criar forks utilizando a ideia central do projeto, e o mais importante, divirta-se!