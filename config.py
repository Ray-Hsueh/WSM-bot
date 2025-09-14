RADIO_STREAM_URL = 'https://stream01048.westreamradio.com/wsm-am-mp3'
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}
