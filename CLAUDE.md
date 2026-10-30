# kvmsync - contexto do projeto

Daemon Python que sincroniza a troca de host Bluetooth entre o teclado
AULA F75 (fn+1 = Linux, fn+2 = Windows) e o mouse Logitech MX Vertical.
Cada máquina roda seu próprio daemon e, ao detectar a troca do teclado,
envia HID++ CHANGE_HOST (feature 0x1814) para o mouse.

Fluxo esperado:
- Estou no Linux, aperto fn+2: teclado e mouse vão para o Windows.
- Estou no Windows, aperto fn+1: teclado e mouse vão para o Linux.

## Estado atual

- Linux: funcionando. `kvmsync/events_linux.py` escuta o BlueZ via D-Bus
  (`org.bluez.Device1.Connected`), roda como serviço systemd
  (`systemd/kvmsync.service`).
- Windows: QUEBRADO. `kvmsync/events_windows.py` não detecta a troca.
  - A versão com SetupAPI (`DBT_DEVICEREMOVECOMPLETE`) nunca dispara para
    desconexão Bluetooth.
  - A versão atual com WMI está errada: procura VID/PID no `Caption`
    (fica no `DeviceID`) e lê `ConnectionState`, que não existe em
    `Win32_PnPEntity`. Resultado: "Aula75 keyboard not found in WMI"
    mesmo com o teclado conectado.

## Fatos sobre o teclado (lidos do BlueZ no Linux)

- Nome: `AULA-F75 5.0 KB`
- Bluetooth LE (endereço random), MAC no Linux `E3:34:CC:0D:A4:0F`
- Modalias `usb:v3554pFA07d6701` -> VID 0x3554, PID 0xFA07 via BLE
  (PID 0xFA09 é o dongle 2.4G USB)
- Teclados multi-host costumam usar MAC diferente por canal, então no
  Windows o MAC provavelmente é outro.

## Próximo passo (fazer no Windows)

Descobrir qual sinal muda de verdade quando o teclado troca de host,
antes de reescrever a detecção. Rodar no PowerShell, apertar fn+1,
esperar 5s, fn+2, esperar 5s, e analisar a saída:

```powershell
$prev = ""
while ($true) {
  $snap = Get-PnpDevice | Where-Object {
    $_.InstanceId -match '3554|E334CC0DA40F' -or $_.FriendlyName -like '*AULA*'
  } | ForEach-Object {
    $c = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName '{83DA6326-97A6-4088-9453-A1923F573B29} 15' -ErrorAction SilentlyContinue).Data
    "{0,-8} present={1,-5} connected={2,-5} {3} | {4}" -f $_.Status, $_.Present, $c, $_.FriendlyName, $_.InstanceId
  } | Out-String
  if ($snap -ne $prev) { "==== $(Get-Date -Format HH:mm:ss) ===="; $snap; $prev = $snap }
  Start-Sleep 1
}
```

Também vale checar se o teclado some do `hid.enumerate(0x3554, 0xFA07)`
quando desconectado. Se sim, dá para detectar só com hidapi (dependência
que o projeto já tem) e remover o uso de `wmi`.

Depois de escolher o sinal: reescrever `events_windows.py` com ele,
testar E2E (fn+1 / fn+2 com o mouse trocando de fato) e conferir também
que o envio do CHANGE_HOST pelo hidapi acha a interface HID++ certa do
mouse (usage page 0xFF00 vendor, não 0x01).

## Convenções

- Python, hidapi como dependência principal; módulos por plataforma.
- Testes: `python -m pytest tests/`
- Não usar travessão; usar "-".
