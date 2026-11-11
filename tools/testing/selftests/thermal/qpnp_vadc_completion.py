#!/usr/bin/env python3
"""Compile the actual ADC ISR and check completion with a blocked workqueue."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[4]
s = (ROOT / 'drivers/hwmon/qpnp-adc-voltage.c').read_text()

def function(name):
 start=s.index('static ',s.index(name)-40);start=s.rfind('\nstatic ',0,s.index(name))+1
 opening=s.index('{',s.index(name));level=1;i=opening+1
 while level:
  level+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[start:i]

work = function('qpnp_vadc_work(') if 'static void qpnp_vadc_work(' in s else ''
irq = function('qpnp_vadc_isr(')
PREAMBLE = '\n#include <stdbool.h>\n#include <stddef.h>\n#include <stdio.h>\n#include <stdlib.h>\nstruct completion { unsigned int done; };\nstruct work_struct { void (*function)(struct work_struct *); };\nstruct qpnp_adc { struct completion adc_rslt_completion; };\nstruct qpnp_vadc_chip { bool valid; struct qpnp_adc *adc; struct work_struct trigger_completion_work; };\nstatic struct work_struct *pending;\n#define container_of(ptr, type, member) ((type *)((char *)(ptr)-offsetof(type,member)))\n#define IRQ_HANDLED 1\n#define irqreturn_t int\nstatic int qpnp_vadc_is_valid(struct qpnp_vadc_chip *vadc) { return vadc->valid ? 0 : -1; }\nstatic void complete(struct completion *value) { value->done++; }\nstatic void schedule_work(struct work_struct *work) { pending=work; }\n'
MAIN = '\nint main(void) {\n struct qpnp_adc adc={0};\n struct qpnp_vadc_chip chip={.valid=true,.adc=&adc};\n SET_WORK\n int healthy=qpnp_vadc_isr(0,&chip);\n if(pending) { pending->function(pending); pending=NULL; }\n if(healthy!=IRQ_HANDLED || adc.adc_rslt_completion.done!=1) return 2;\n for(int i=0;i<10000;i++) {\n  adc.adc_rslt_completion.done=0;\n  qpnp_vadc_isr(0,&chip);\n  /* The shared workqueue deliberately cannot run during this conversion. */\n  if(adc.adc_rslt_completion.done!=1) { puts("completion blocked behind workqueue"); return 1; }\n  if(pending) return 3;\n }\n chip.valid=false;adc.adc_rslt_completion.done=0;\n qpnp_vadc_isr(0,&chip);\n if(pending) { pending->function(pending); pending=NULL; }\n if(adc.adc_rslt_completion.done) return 4;\n puts("10000 fresh conversions completed; invalid ADC still rejected");\n return 0;\n}\n'
with tempfile.TemporaryDirectory(prefix='vadc-completion-') as directory:
  source = Path(directory) / 'test.c'
  binary = Path(directory) / 'test'
  setup = 'chip.trigger_completion_work.function=qpnp_vadc_work;' if work else ''
  source.write_text(PREAMBLE + work + '\n' + irq + '\n' + MAIN.replace('SET_WORK', setup))
  subprocess.run(['gcc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                  '-Wno-unused-function', str(source), '-o', str(binary)], check=True)
  subprocess.run([str(binary)], check=True)
