import asyncio
import edge_tts

async def main():
    text = "Hello world. This is a test."
    voice = "en-US-JennyNeural"

    print("STARTING EDGE TTS TEST")
    print("Text:", text)
    print("Voice:", voice)

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save("test_audio.mp3")

    print("DONE. File created: test_audio.mp3")

asyncio.run(main())