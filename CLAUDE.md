# kvmsync - contexto do projeto

Daemon Python que sincroniza a troca de host Bluetooth entre o teclado
AULA F75 (fn+1 = Linux, fn+2 = Windows) e o mouse Logitech MX Vertical.
Cada máquina roda seu próprio daemon e, ao detectar a troca do teclado,
envia HID++ CHANGE_HOST (feature 0x1814) para o mouse.

Fluxo esperado:
- Estou no Linux, aperto fn+2: teclado e mouse vão para o Windows.
- Estou no Windows, aperto fn+1: teclado e mouse vão para o Linux.

## Estado atual

Regra central: quem move o mouse é a máquina que o teclado ACABOU DE
DEIXAR (é a única que ainda está conectada ao mouse). Por isso os dois
daemons precisam estar rodando.

- Lógica comum: `kvmsync/presence.py` (`PresenceWatcher`) faz polling a
  cada 0.2s de uma função "teclado presente?", com debounce (1s ausente /
  0.5s presente). Saiu -> CHANGE_HOST(slot do outro host); chegou ->
  CHANGE_HOST(slot local).
- Linux: FUNCIONANDO (fn+2 testado E2E em 2026-10-30, mouse foi pro
  Windows). `events_linux.py` lê `org.bluez.Device1.Connected` por
  polling (sinais do dbus-python exigem main loop GLib e quebravam).
  Serviço systemd `systemd/kvmsync.service`, regra udev
  `systemd/70-kvmsync-hidraw.rules` instalada.
- Windows: `events_windows.py` faz polling de
  `hid.enumerate(0x3554, 0xFA07)` (some em ~1s quando o teclado sai).
  WMI/PnP descartados (propriedade "connected" atrasa vários segundos).
  Na última tentativa de fn+1 no Windows o mouse NÃO voltou para o Linux,
  provavelmente porque o daemon do Windows não estava rodando. Próximo
  passo: rodar `python -m kvmsync -c config.toml -v`, testar fn+1 e,
  funcionando, configurar o início automático (ver README, seção Windows).
- Envio do CHANGE_HOST: `kvmsync/mouse.py`. Resolve o índice da feature
  0x1814 via IRoot (no MX Vertical é 0x0C). HID++ do mouse por BLE fica
  na usage page 0xFF43. No Linux usa o módulo `hidraw` do pacote hidapi
  (o módulo `hid` lá é libusb e não enxerga Bluetooth).

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
