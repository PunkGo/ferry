from __future__ import annotations
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
import asyncio
from enum import Enum
from typing import Literal
from pydantic import BaseModel, RootModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "ferry" / "src"))
from ferry_mcp.adapter import FerryAdapter
from ferry_mcp.server import create_server, _sandbox

class NoAdvisory:
 async def start(self): pass
 async def close(self): pass
 def add_to(self, result): return result

class BrokenAdvisory:
 def __init__(self): raise RuntimeError("controlled advisory construction failure")

@dataclass
class Event: method: str; payload: object
class Status(Enum): completed="completed"; interrupted="interrupted"; failed="failed"
class ActiveThreadStatus(BaseModel): type: Literal["active"] = "active"
class IdleThreadStatus(BaseModel): type: Literal["idle"] = "idle"
class SystemErrorThreadStatus(BaseModel): type: Literal["systemError"] = "systemError"
class ThreadStatus(RootModel[ActiveThreadStatus | IdleThreadStatus | SystemErrorThreadStatus]): pass
class Turn:
 def __init__(self, thread, ident, fail=False): self.thread,self.thread_id,self.id,self.fail,self.queue,self.cleanup_failure=thread,thread.id,ident,fail,asyncio.Queue(),False; self.queue.put_nowait(Event("turn/started", {}))
 async def stream(self):
  try:
   while True:
    event=await self.queue.get()
    if event.method=="turn/started": self.thread.turn_ready=True
    if event.method=="thread/status/idle": self.thread.liveness="idle"
    yield event
    if self.fail: raise RuntimeError("controlled terminal stream failure")
    if event.method=="turn/completed": return
  finally:
   if self.cleanup_failure: raise RuntimeError("controlled terminal cleanup failure")
 async def steer(self, _):
  if not self.thread.turn_ready: raise RuntimeError("native active turn is not registered")
  if self.thread.liveness != "active": raise RuntimeError("no active turn to steer")
  if self.thread.read_gate is not None: self.thread.read_gate.set()
  self.thread.liveness="idle"; self.queue.put_nowait(Event("turn/completed", {"status":Status.completed}))
 async def interrupt(self):
  if not self.thread.turn_ready: raise RuntimeError("native active turn is not registered")
  if self.thread.liveness != "active": raise RuntimeError("no active turn to interrupt")
  if self.thread.read_gate is not None: self.thread.read_gate.set()
  self.fail=False; self.thread.liveness="idle"; self.queue.put_nowait(Event("turn/completed", {"status":Status.interrupted}))
class Thread:
 def __init__(self, client, ident, cwd, provider, model=None): self.client,self.id,self.cwd,self.provider,self.model,self.read_count,self.liveness,self.read_failure,self.read_timeout,self.read_gate,self.unexpected_status,self.system_error,self.turn_ready=client,ident,cwd,provider,model,0,"active",False,False,None,False,False,False
 async def read(self, include_turns=False):
  self.read_count+=1
  if include_turns: raise RuntimeError("terminal path must not read history")
  if self.read_failure and self.read_count == 2: raise RuntimeError("controlled native thread read failure")
  if self.read_timeout:
   if self.read_count > 2: raise AssertionError("duplicate native liveness read")
   self.read_gate=asyncio.Event(); await self.read_gate.wait()
  native_status=SimpleNamespace(type="unexpected") if self.unexpected_status else (SystemErrorThreadStatus() if self.system_error else (IdleThreadStatus() if self.liveness=="idle" else ActiveThreadStatus()))
  status=SimpleNamespace(root=native_status) if self.unexpected_status else ThreadStatus(native_status)
  return SimpleNamespace(thread=SimpleNamespace(model_provider="wrong" if self.provider=="mismatch" else self.provider,model="different-model" if self.model=="mismatch-model" else self.model,cwd=SimpleNamespace(root=self.cwd),status=status))
 async def turn(self, brief, **_):
  if self.model=="mismatch-model": raise AssertionError("turn must not run after model mismatch")
  self.liveness="active"
  self.turn_ready=False
  ident=f"turn-{self.client.n}"; self.client.n+=1
  turn=Turn(self,ident,brief=="failure")
  if brief=="failed-terminal": turn.queue.put_nowait(Event("turn/completed", {"status":Status.failed,"error":{"message":"native failed cause"}}))
  if brief=="missing-terminal": turn.queue.put_nowait(Event("turn/completed", {}))
  if brief=="huge-terminal": turn.queue.put_nowait(Event("turn/completed", {"status":Status.completed,"final_response":"x"*9000}))
  if brief=="cleanup-failure": turn.cleanup_failure=True; turn.queue.put_nowait(Event("turn/completed", {"status":Status.completed}))
  if brief=="idle-backlog":
   self.liveness="idle"; turn.queue.put_nowait(Event("item/updated", {"queued":True})); turn.queue.put_nowait(Event("turn/completed", {"status":Status.completed}))
  if brief=="reasoning-noise":
   for _ in range(64):
    turn.queue.put_nowait(Event("item/reasoning/textDelta", {"text":"noise"})); turn.queue.put_nowait(Event("item/reasoning/summaryTextDelta", {"text":"noise"}))
   turn.queue.put_nowait(Event("item/agentMessage/delta", {"text":"retained"})); turn.queue.put_nowait(Event("item/plan/delta", {"text":"retained"})); turn.queue.put_nowait(Event("item/commandExecution/outputDelta", {"text":"retained"})); turn.queue.put_nowait(Event("turn/plan/updated", {"plan":[]})); turn.queue.put_nowait(Event("thread/tokenUsage/updated", {"total":1})); turn.queue.put_nowait(Event("warning", {"message":"retained"})); turn.queue.put_nowait(Event("item/updated", {"retained":True})); turn.queue.put_nowait(Event("turn/completed", {"status":Status.completed}))
  if brief=="reasoning-failed-terminal":
   for _ in range(64):
    turn.queue.put_nowait(Event("item/reasoning/textDelta", {"text":"noise"})); turn.queue.put_nowait(Event("item/reasoning/summaryTextDelta", {"text":"noise"}))
   turn.queue.put_nowait(Event("error", {"error":{"message":"reasoning failure cause"}})); turn.queue.put_nowait(Event("item/updated", {"retained":True})); turn.queue.put_nowait(Event("turn/completed", {"status":Status.failed,"error":{"message":"reasoning failure cause"}}))
  if brief=="liveness-transition":
   turn.queue.put_nowait(Event("thread/status/idle", {})); turn.queue.put_nowait(Event("turn/completed", {"status":Status.completed}))
  if brief=="native-read-failure": self.read_failure=True
  if brief=="native-read-timeout": self.read_timeout=True
  if brief=="unexpected-status": self.unexpected_status=True
  if brief=="system-error": self.system_error=True; turn.queue.put_nowait(Event("item/updated", {"queued":True})); turn.queue.put_nowait(Event("turn/completed", {"status":Status.failed,"error":{"message":"native system error cause"}}))
  return turn
class Client:
 def __init__(self): self.n=1; self.threads={}
 async def thread_start(self, cwd, model_provider, model=None, **_):
  ident=f"thread-{self.n}"; self.n+=1; self.threads[ident]=Thread(self,ident,cwd,model_provider,model); return self.threads[ident]
 async def thread_resume(self, thread_id, cwd, model_provider, model=None, **_): return self.threads.setdefault(thread_id,Thread(self,thread_id,cwd,model_provider,model))
 async def close(self): pass

server=create_server(lambda: FerryAdapter(Client(), _sandbox), advisory_factory=BrokenAdvisory if os.environ.get("FERRY_FAKE_BROKEN_ADVISORY") else NoAdvisory)
if __name__ == "__main__": server.run(transport="stdio")
