import shlex
import subprocess

headers_str = "User-Agent: Mozilla/5.0\r\nAccept: */*\r\n"
opts = f'-headers "{headers_str}" -reconnect 1'
print(shlex.split(opts))
