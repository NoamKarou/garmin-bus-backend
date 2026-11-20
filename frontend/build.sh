SDK="C:/Users/yeled/AppData/Roaming/Garmin/ConnectIQ/Sdks/connectiq-sdk-win-9.3.0-2026-10-20-95888f262"
"$SDK/bin/monkeyc" -f monkey.jungle -o bin/bus.prg -d vivoactive5 -y developer_key.der
"$SDK/bin/monkeydo" bin/bus.prg vivoactive5
