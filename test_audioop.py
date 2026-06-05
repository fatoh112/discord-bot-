import audioop
print(dir(audioop))
try:
    res = audioop.mul(b'\x00\x00\x00\x00', 2, 0.5)
    print("audioop.mul succeeded! length:", len(res))
except Exception as e:
    print("Error:", e)
