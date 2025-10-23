# Script run
# conda activate arena_battle
# python -m game_server.main   -> run game server according to config in rooms.json, press R to switch room

# python -m ai_bot.main --player-id BOT1 --room-id room_001 --room-password abc123 --auto-load
# python -m ai_bot.main --player-id BOT2 --room-id room_001 --room-password abc123 --auto-load
# Add --auto-load to resume from last save checkpoint in model/checkpoint
# It will wait until other players join then auto start the game
# This model i use the PPO algorithm so it is a little bit stupid, u can try another one to learn for ai_bot 
# when disconnect, it will auto save the model to model/checkpoint.

# python -m ai_bot.main_player --player_id PLAYER --room room_001 --password abc123

#PVE
# python -m ai_bot.main_player --player_id PLAYER --room room_pve --password pve123
# python -m ai_bot.main --player-id BOT1 --room-id room_pve --room-password pve123

# Log du lieu grpc truoc khi gui, moi file chua 5p du lieu
# Dong goi lai ai_bot
# Tao room, timeout 30p, set password, num player toi da
# ai_bot them  logic ket noi phong
# already fix the error game stop when all the bot died