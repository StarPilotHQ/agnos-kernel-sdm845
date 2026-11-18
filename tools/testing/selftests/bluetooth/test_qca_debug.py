#!/usr/bin/env python3
"""Exercise the registered QCA ACL receiver for every header and alignment."""
from pathlib import Path
import re
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[4]
source = (root / 'drivers/bluetooth/hci_qca.c').read_text()
receiver = re.search(r'\{ H4_RECV_ACL,\s+\.recv = (\w+)', source).group(1)
handler = ''
if receiver != 'hci_recv_frame':
  start = source.index('static int ' + receiver + '(')
  opening = source.index('{', start)
  depth, end = 1, opening + 1
  while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
  handler = source[start:end]
  handler = re.search(r'^#define QCA_DEBUG_HANDLE\s+\S+', source, re.M).group() + '\n' + handler

program = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
struct hci_dev { unsigned int unused; };
struct sk_buff { unsigned char *data; };
static unsigned int normal, diagnostic;
static struct hci_dev *expected_dev;
static struct sk_buff *expected_skb;
static uint16_t get_unaligned_le16(const void *pointer)
{ const unsigned char *p = pointer; return p[0] | ((uint16_t)p[1] << 8); }
static int hci_recv_frame(struct hci_dev *dev, struct sk_buff *skb)
{ assert(dev == expected_dev && skb == expected_skb); ++normal; return 23; }
static int hci_recv_diag(struct hci_dev *dev, struct sk_buff *skb)
{ assert(dev == expected_dev && skb == expected_skb); ++diagnostic; return 47; }
'''
program += handler + '\nstatic int receive(struct hci_dev *d, struct sk_buff *s) { return ' + receiver + '(d, s); }\n'
program += r'''
int main(void)
{
  struct hci_dev dev = {0};
  unsigned int cases = 0, failed = 0;
  expected_dev = &dev;
  for (unsigned int offset = 0; offset < 2; ++offset) {
    for (unsigned int header = 0; header <= UINT16_MAX; ++header) {
      unsigned char data[16], before[16];
      memset(data, 0xa5, sizeof(data));
      data[offset] = header & 0xff; data[offset + 1] = header >> 8;
      memcpy(before, data, sizeof(data));
      struct sk_buff skb = {.data = data + offset};
      expected_skb = &skb; normal = diagnostic = 0;
      int result = receive(&dev, &skb);
      unsigned int debug = header == 0x2edc;
      failed += result != (debug ? 47 : 23) || diagnostic != debug || normal != (debug ^ 1U);
      assert(skb.data == data + offset && !memcmp(data, before, sizeof(data)));
      ++cases;
    }
  }
  printf("%u header/alignment cases; %u failed\n", cases, failed);
  return failed != 0;
}
'''
with tempfile.TemporaryDirectory(prefix='qca-debug-') as directory:
  c = Path(directory) / 'check.c'
  binary = Path(directory) / 'check'
  c.write_text(program)
  subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function', str(c), '-o', str(binary)], check=True)
  subprocess.run([str(binary)], check=True)
