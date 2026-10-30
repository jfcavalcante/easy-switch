# kvmsync - contexto do projeto

Daemon Python que sincroniza a troca de host Bluetooth entre o teclado
AULA F75 (fn+1 = Linux, fn+2 = Windows) e o mouse Logitech MX Vertical.
Cada máquina roda seu próprio daemon e, ao detectar a troca do teclado,
envia HID++ CHANGE_HOST (feature 0x1814) para o mouse.

Fluxo esperado:
- Estou no Linux, aperto fn+2: teclado e mouse vão para o Windows.
- Estou no Windows, aperto fn+1: teclado e mouse vão para o Linux.

## Estado atual

- Windows: funcionando (testado E2E com fn+1). `kvmsync/events_windows.py`
  faz polling de `hid.enumerate(0x3554, 0xFA07)`: lista vazia = teclado
  saiu do Windows (some em ~1s). Debounce: 1s ausente / 0.5s presente.
  WMI/PnP descartados (propriedade "connected" atrasa vários segundos).
- Envio do CHANGE_HOST: `kvmsync/mouse.py`, comum às duas plataformas, via
  hidapi (`hid.device()`, pacote `hidapi`). Resolve o índice da feature
  0x1814 via IRoot (no MX Vertical é 0x0C). No Windows, por BLE, o HID++
  do mouse fica na usage page 0xFF43.
- Linux: detecção via BlueZ D-Bus (`org.bluez.Device1.Connected`), serviço
  systemd (`systemd/kvmsync.service`). Antes NÃO enviava CHANGE_HOST
  (`hidraw=None`); agora usa `kvmsync/mouse.py`. Falta testar fn+2 no
  Linux: instalar `systemd/70-kvmsync-hidraw.rules` em
  /etc/udev/rules.d/ e reiniciar o serviço.

## Fatos sobre o teclado (lidos do BlueZ no Linux)

- Nome: `AULA-F75 5.0 KB`
- Bluetooth LE (endereço random), MAC no Linux `E3:34:CC:0D:A4:0F`
- Modalias `usb:v3554pFA07d6701` -> VID 0x3554, PID 0xFA07 via BLE
  (PID 0xFA09 é o dongle 2.4G USB)
- Teclados multi-host costumam usar MAC diferente por canal, então no
  Windows o MAC provavelmente é outro.

## Fatos sobre o teclado no Windows

- MAC BLE no Windows: `FE3AA882861E` (diferente do Linux)
- 6 coleções HID com VID 0x3554 / PID 0xFA07 quando conectado

## Convenções

- Python, hidapi como dependência principal; módulos por plataforma.
- Testes: `python -m pytest tests/`
- Não usar travessão; usar "-".
