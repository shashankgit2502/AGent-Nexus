08:11:29 INFO     sqlalchemy.engine.Engine  COMMIT
08:12:37 ERROR    app.graph.nodes.agent_turn  agent_turn failed for agent=73069a2f-5299-4e09-be89-bf1a462f2631 round=1; recording abstention
Traceback (most recent call last):
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpx\_transports\default.py", line 101, in map_httpcore_exceptions
    yield
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpx\_transports\default.py", line 250, in handle_request
    resp = self._pool.handle_request(req)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpcore\_sync\connection_pool.py", line 256, in handle_request
    raise exc from None
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpcore\_sync\connection_pool.py", line 236, in handle_request
    response = connection.handle_request(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpcore\_sync\connection.py", line 103, in handle_request
    return self._connection.handle_request(request)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpcore\_sync\http11.py", line 136, in handle_request
    raise exc
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpcore\_sync\http11.py", line 106, in handle_request
    ) = self._receive_response_headers(**kwargs)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpcore\_sync\http11.py", line 177, in _receive_response_headers
    event = self._receive_event(timeout=timeout)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpcore\_sync\http11.py", line 231, in _receive_event
    raise RemoteProtocolError(msg)
httpcore.RemoteProtocolError: Server disconnected without sending a response.

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "E:\Agent Hackathon\nex-agi\backend\app\graph\nodes\agent_turn.py", line 138, in agent_turn_node
    update = runner.run(agent_id, payload)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\nex-agi\backend\app\agents\mesh.py", line 54, in run
    return run_agent_turn(agent, cfg, blackboard)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\nex-agi\backend\app\agents\runtime.py", line 233, in run_agent_turn
    result = agent.invoke({"messages": [HumanMessage(content=message)]})
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\main.py", line 3928, in invoke
    for chunk in self.stream(
                 ^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\main.py", line 2982, in stream
    for _ in runner.tick(
             ^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\_runner.py", line 344, in tick
    _panic_or_proceed(
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\_runner.py", line 687, in _panic_or_proceed
    raise exc
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\_executor.py", line 80, in done
    task.result()
  File "C:\Users\Shashank Singh\AppData\Local\Programs\Python\Python312\Lib\concurrent\futures\_base.py", line 449, in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Shashank Singh\AppData\Local\Programs\Python\Python312\Lib\concurrent\futures\_base.py", line 401, in __get_result
    raise self._exception
  File "C:\Users\Shashank Singh\AppData\Local\Programs\Python\Python312\Lib\concurrent\futures\thread.py", line 58, in run
    result = self.fn(*self.args, **self.kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\_retry.py", line 617, in run_with_retry
    return task.proc.invoke(task.input, config)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\_internal\_runnable.py", line 684, in invoke
    input = context.run(step.invoke, input, config, **kwargs)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\_internal\_runnable.py", line 426, in invoke
    ret = self.func(*args, **kwargs)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 822, in _func
    outputs = list(
              ^^^^^
  File "C:\Users\Shashank Singh\AppData\Local\Programs\Python\Python312\Lib\concurrent\futures\_base.py", line 619, in result_iterator
    yield _result_or_cancel(fs.pop())
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Shashank Singh\AppData\Local\Programs\Python\Python312\Lib\concurrent\futures\_base.py", line 317, in _result_or_cancel
    return fut.result(timeout)
           ^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Shashank Singh\AppData\Local\Programs\Python\Python312\Lib\concurrent\futures\_base.py", line 456, in result
    return self.__get_result()
           ^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Shashank Singh\AppData\Local\Programs\Python\Python312\Lib\concurrent\futures\_base.py", line 401, in __get_result
    raise self._exception
  File "C:\Users\Shashank Singh\AppData\Local\Programs\Python\Python312\Lib\concurrent\futures\thread.py", line 58, in run
    result = self.fn(*self.args, **self.kwargs)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\runnables\config.py", line 650, in _wrapped_fn
    return contexts.pop().run(fn, *args)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 1061, in _run_one
    content = _handle_tool_error(e, flag=self._handle_tool_errors)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 434, in _handle_tool_error
    content = flag(e)  # type: ignore [assignment, call-arg]
              ^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 391, in _default_handle_tool_errors
    raise e
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 1055, in _run_one
    return self._wrap_tool_call(tool_request, execute)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\deepagents\middleware\filesystem.py", line 2232, in wrap_tool_call
    tool_result = handler(request)
                  ^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 1051, in execute
    return self._execute_tool_sync(req, input_type, config)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 1006, in _execute_tool_sync
    content = _handle_tool_error(e, flag=self._handle_tool_errors)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 434, in _handle_tool_error
    content = flag(e)  # type: ignore [assignment, call-arg]
              ^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 391, in _default_handle_tool_errors
    raise e
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\prebuilt\tool_node.py", line 958, in _execute_tool_sync
    response = tool.invoke(call_args, config)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\tools\base.py", line 640, in invoke
    return self.run(tool_input, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\tools\base.py", line 1002, in run
    raise error_to_raise
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\tools\base.py", line 968, in run
    response = context.run(self._run, *tool_args, **tool_kwargs)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\tools\structured.py", line 97, in _run
    return self.func(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\deepagents\middleware\subagents.py", line 693, in task
    result = subagent.invoke(subagent_state, subagent_config)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\main.py", line 3928, in invoke
    for chunk in self.stream(
                 ^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\main.py", line 2982, in stream
    for _ in runner.tick(
             ^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\_runner.py", line 207, in tick
    run_with_retry(
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\_retry.py", line 617, in run_with_retry
    return task.proc.invoke(task.input, config)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\_internal\_runnable.py", line 684, in invoke
    input = context.run(step.invoke, input, config, **kwargs)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\_internal\_runnable.py", line 426, in invoke
    ret = self.func(*args, **kwargs)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 1424, in model_node
    result = wrap_model_call_handler(request, _execute_model_sync)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 310, in composed
    outer_result = outer(request, inner_handler)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\middleware\todo.py", line 256, in wrap_model_call
    return handler(request.override(system_message=new_system_message))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 300, in inner_handler
    inner_result = inner(req, handler)
                   ^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 310, in composed
    outer_result = outer(request, inner_handler)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\deepagents\middleware\filesystem.py", line 1820, in wrap_model_call
    return handler(request)
           ^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 300, in inner_handler
    inner_result = inner(req, handler)
                   ^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 310, in composed
    outer_result = outer(request, inner_handler)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\deepagents\middleware\summarization.py", line 1060, in wrap_model_call
    return handler(request.override(messages=truncated_messages))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 300, in inner_handler
    inner_result = inner(req, handler)
                   ^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_anthropic\middleware\prompt_caching.py", line 165, in wrap_model_call
    return handler(request)
           ^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 1393, in _execute_model_sync
    output = model_.invoke(messages)
             ^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\runnables\base.py", line 6004, in invoke
    return self.bound.invoke(
           ^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 476, in invoke
    self.generate_prompt(
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 1849, in generate_prompt
    return self.generate(prompt_messages, stop=stop, callbacks=callbacks, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 1656, in generate
    self._generate_with_cache(
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 1994, in _generate_with_cache
    result = self._generate(
             ^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_openrouter\chat_models.py", line 510, in _generate
    response = self.client.chat.send(messages=sdk_messages, **params)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\openrouter\chat.py", line 567, in send
    http_res = self.do_request(
               ^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\openrouter\basesdk.py", line 291, in do_request
    http_res = utils.retry(do, utils.Retries(retry_config[0], retry_config[1]))
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\openrouter\utils\retries.py", line 164, in retry
    return retry_with_backoff(
           ^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\openrouter\utils\retries.py", line 238, in retry_with_backoff
    raise exception.inner
  File "E:\Agent Hackathon\.venv\Lib\site-packages\openrouter\utils\retries.py", line 132, in do_request
    res = func()
          ^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\openrouter\basesdk.py", line 259, in do
    raise e
  File "E:\Agent Hackathon\.venv\Lib\site-packages\openrouter\basesdk.py", line 254, in do
    http_res = client.send(req, stream=stream)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpx\_client.py", line 914, in send
    response = self._send_handling_auth(
               ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpx\_client.py", line 942, in _send_handling_auth
    response = self._send_handling_redirects(
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpx\_client.py", line 979, in _send_handling_redirects
    response = self._send_single_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpx\_client.py", line 1014, in _send_single_request
    response = transport.handle_request(request)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpx\_transports\default.py", line 249, in handle_request
    with map_httpcore_exceptions():
         ^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Shashank Singh\AppData\Local\Programs\Python\Python312\Lib\contextlib.py", line 158, in __exit__
    self.gen.throw(value)
  File "E:\Agent Hackathon\.venv\Lib\site-packages\httpx\_transports\default.py", line 118, in map_httpcore_exceptions
    raise mapped_exc(message) from exc
httpx.RemoteProtocolError: Server disconnected without sending a response.
During task with name 'model' and id 'a0d557dc-d87f-e47c-be54-edba02b27dfd'
During task with name 'tools' and id '074f463a-43aa-6fac-eae6-e0a2e8f19bb2'
2026-06-20 08:12:37,927 INFO sqlalchemy.engine.Engine BEGIN (implicit)
08:12:37 INFO     sqlalchemy.engine.Engine  BEGIN (implicit)
2026-06-20 08:12:37,927 INFO sqlalchemy.engine.Engine SELECT set_config('app.current_org', $1, true)
08:12:37 INFO     sqlalchemy.engine.Engine  SELECT set_config('app.current_org', $1, true)
2026-06-20 08:12:37,927 INFO sqlalchemy.engine.Engine [cached since 132.8s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
08:12:37 INFO     sqlalchemy.engine.Engine  [cached since 132.8s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
2026-06-20 08:12:37,934 INFO sqlalchemy.engine.Engine INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
08:12:37 INFO     sqlalchemy.engine.Engine  INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
2026-06-20 08:12:37,934 INFO sqlalchemy.engine.Engine [cached since 130s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 39, 'agent_turn_start', '{"agent_id": "73069a2f-5299-4e09-be89-bf1a462f2631", "round": 1}', datetime.datetime(2026, 6, 20, 2, 42, 37, 920960, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
08:12:37 INFO     sqlalchemy.engine.Engine  [cached since 130s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 39, 'agent_turn_start', '{"agent_id": "73069a2f-5299-4e09-be89-bf1a462f2631", "round": 1}', datetime.datetime(2026, 6, 20, 2, 42, 37, 920960, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
2026-06-20 08:12:37,938 INFO sqlalchemy.engine.Engine COMMIT
08:12:37 INFO     sqlalchemy.engine.Engine  COMMIT
2026-06-20 08:12:37,948 INFO sqlalchemy.engine.Engine BEGIN (implicit)
08:12:37 INFO     sqlalchemy.engine.Engine  BEGIN (implicit)
2026-06-20 08:12:37,948 INFO sqlalchemy.engine.Engine SELECT set_config('app.current_org', $1, true)
08:12:37 INFO     sqlalchemy.engine.Engine  SELECT set_config('app.current_org', $1, true)
2026-06-20 08:12:37,948 INFO sqlalchemy.engine.Engine [cached since 132.8s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
08:12:37 INFO     sqlalchemy.engine.Engine  [cached since 132.8s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
2026-06-20 08:12:37,954 INFO sqlalchemy.engine.Engine INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
08:12:37 INFO     sqlalchemy.engine.Engine  INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
2026-06-20 08:12:37,954 INFO sqlalchemy.engine.Engine [cached since 130.1s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 40, 'error', '{"scope": "agent_turn", "agent_id": "73069a2f-5299-4e09-be89-bf1a462f2631", "round": 1, "message": "Server disconnected without sending a response."}', datetime.datetime(2026, 6, 20, 2, 42, 37, 942449, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
08:12:37 INFO     sqlalchemy.engine.Engine  [cached since 130.1s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 40, 'error', '{"scope": "agent_turn", "agent_id": "73069a2f-5299-4e09-be89-bf1a462f2631", "round": 1, "message": "Server disconnected without sending a response."}', datetime.datetime(2026, 6, 20, 2, 42, 37, 942449, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
2026-06-20 08:12:37,957 INFO sqlalchemy.engine.Engine COMMIT
08:12:37 INFO     sqlalchemy.engine.Engine  COMMIT
INFO:     Shutting down
INFO:     connection closed
INFO:     Waiting for background tasks to complete. (CTRL+C to force quit)
08:16:34 ERROR    app.graph.nodes.agent_turn  agent_turn failed for agent=1016f4ec-c4ea-4744-bee8-0cfbf5963320 round=1; recording abstention
Traceback (most recent call last):
  File "E:\Agent Hackathon\nex-agi\backend\app\graph\nodes\agent_turn.py", line 138, in agent_turn_node
    update = runner.run(agent_id, payload)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\nex-agi\backend\app\agents\mesh.py", line 54, in run
    return run_agent_turn(agent, cfg, blackboard)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\nex-agi\backend\app\agents\runtime.py", line 233, in run_agent_turn
    result = agent.invoke({"messages": [HumanMessage(content=message)]})
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\main.py", line 3928, in invoke
    for chunk in self.stream(
                 ^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\main.py", line 2982, in stream
    for _ in runner.tick(
             ^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\_runner.py", line 207, in tick
    run_with_retry(
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\pregel\_retry.py", line 617, in run_with_retry
    return task.proc.invoke(task.input, config)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\_internal\_runnable.py", line 684, in invoke
    input = context.run(step.invoke, input, config, **kwargs)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langgraph\_internal\_runnable.py", line 426, in invoke
    ret = self.func(*args, **kwargs)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 1424, in model_node
    result = wrap_model_call_handler(request, _execute_model_sync)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 310, in composed
    outer_result = outer(request, inner_handler)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\middleware\todo.py", line 256, in wrap_model_call
    return handler(request.override(system_message=new_system_message))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 300, in inner_handler
    inner_result = inner(req, handler)
                   ^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 310, in composed
    outer_result = outer(request, inner_handler)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\deepagents\middleware\filesystem.py", line 1820, in wrap_model_call
    return handler(request)
           ^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 300, in inner_handler
    inner_result = inner(req, handler)
                   ^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 310, in composed
    outer_result = outer(request, inner_handler)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\deepagents\middleware\subagents.py", line 856, in wrap_model_call
    return handler(request.override(system_message=new_system_message))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 300, in inner_handler
    inner_result = inner(req, handler)
                   ^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 310, in composed
    outer_result = outer(request, inner_handler)
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\deepagents\middleware\summarization.py", line 1060, in wrap_model_call
    return handler(request.override(messages=truncated_messages))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 300, in inner_handler
    inner_result = inner(req, handler)
                   ^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langsmith\run_helpers.py", line 777, in wrapper
    function_result = run_container["context"].run(
                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_anthropic\middleware\prompt_caching.py", line 165, in wrap_model_call
    return handler(request)
           ^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain\agents\factory.py", line 1393, in _execute_model_sync
    output = model_.invoke(messages)
             ^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\runnables\base.py", line 6004, in invoke
    return self.bound.invoke(
           ^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 476, in invoke
    self.generate_prompt(
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 1849, in generate_prompt
    return self.generate(prompt_messages, stop=stop, callbacks=callbacks, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 1656, in generate
    self._generate_with_cache(
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_core\language_models\chat_models.py", line 1994, in _generate_with_cache
    result = self._generate(
             ^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\langchain_openrouter\chat_models.py", line 510, in _generate
    response = self.client.chat.send(messages=sdk_messages, **params)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\Agent Hackathon\.venv\Lib\site-packages\openrouter\chat.py", line 634, in send
    raise errors.PaymentRequiredResponseError(
openrouter.errors.paymentrequiredresponse_error.PaymentRequiredResponseError: This request requires more credits, or fewer max_tokens. You requested up to 65536 tokens, but can only afford 9983. To increase, visit https://openrouter.ai/settings/credits and upgrade to a paid account
During task with name 'model' and id '20c0e532-1bc3-5175-d5ee-d3adb6366810'
2026-06-20 08:16:35,014 INFO sqlalchemy.engine.Engine BEGIN (implicit)
08:16:35 INFO     sqlalchemy.engine.Engine  BEGIN (implicit)
2026-06-20 08:16:35,016 INFO sqlalchemy.engine.Engine SELECT set_config('app.current_org', $1, true)
08:16:35 INFO     sqlalchemy.engine.Engine  SELECT set_config('app.current_org', $1, true)
2026-06-20 08:16:35,016 INFO sqlalchemy.engine.Engine [cached since 369.9s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
08:16:35 INFO     sqlalchemy.engine.Engine  [cached since 369.9s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
2026-06-20 08:16:35,025 INFO sqlalchemy.engine.Engine INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
08:16:35 INFO     sqlalchemy.engine.Engine  INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
2026-06-20 08:16:35,025 INFO sqlalchemy.engine.Engine [cached since 367.1s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 41, 'agent_turn_start', '{"agent_id": "1016f4ec-c4ea-4744-bee8-0cfbf5963320", "round": 1}', datetime.datetime(2026, 6, 20, 2, 46, 35, 3840, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
08:16:35 INFO     sqlalchemy.engine.Engine  [cached since 367.1s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 41, 'agent_turn_start', '{"agent_id": "1016f4ec-c4ea-4744-bee8-0cfbf5963320", "round": 1}', datetime.datetime(2026, 6, 20, 2, 46, 35, 3840, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
2026-06-20 08:16:35,029 INFO sqlalchemy.engine.Engine COMMIT
08:16:35 INFO     sqlalchemy.engine.Engine  COMMIT
08:16:35 DEBUG    app.streaming.websocket  client disconnected from run=706be154-ef75-4976-93f6-d9da8b09fd7b stream
2026-06-20 08:16:35,045 INFO sqlalchemy.engine.Engine BEGIN (implicit)
08:16:35 INFO     sqlalchemy.engine.Engine  BEGIN (implicit)
2026-06-20 08:16:35,045 INFO sqlalchemy.engine.Engine SELECT set_config('app.current_org', $1, true)
08:16:35 INFO     sqlalchemy.engine.Engine  SELECT set_config('app.current_org', $1, true)
2026-06-20 08:16:35,045 INFO sqlalchemy.engine.Engine [cached since 369.9s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
08:16:35 INFO     sqlalchemy.engine.Engine  [cached since 369.9s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
2026-06-20 08:16:35,048 INFO sqlalchemy.engine.Engine INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
08:16:35 INFO     sqlalchemy.engine.Engine  INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
2026-06-20 08:16:35,048 INFO sqlalchemy.engine.Engine [cached since 367.2s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 42, 'error', '{"scope": "agent_turn", "agent_id": "1016f4ec-c4ea-4744-bee8-0cfbf5963320", "round": 1, "message": "This request requires more credits, or fewer max_ ... (8 characters truncated) ... You requested up to 65536 tokens, but can only afford 9983. To increase, visit https://openrouter.ai/settings/credits and upgrade to a paid account"}', datetime.datetime(2026, 6, 20, 2, 46, 35, 34380, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
08:16:35 INFO     sqlalchemy.engine.Engine  [cached since 367.2s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 42, 'error', '{"scope": "agent_turn", "agent_id": "1016f4ec-c4ea-4744-bee8-0cfbf5963320", "round": 1, "message": "This request requires more credits, or fewer max_ ... (8 characters truncated) ... You requested up to 65536 tokens, but can only afford 9983. To increase, visit https://openrouter.ai/settings/credits and upgrade to a paid account"}', datetime.datetime(2026, 6, 20, 2, 46, 35, 34380, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
2026-06-20 08:16:35,055 INFO sqlalchemy.engine.Engine COMMIT
08:16:35 INFO     sqlalchemy.engine.Engine  COMMIT
2026-06-20 08:16:35,069 INFO sqlalchemy.engine.Engine BEGIN (implicit)
08:16:35 INFO     sqlalchemy.engine.Engine  BEGIN (implicit)
2026-06-20 08:16:35,069 INFO sqlalchemy.engine.Engine SELECT set_config('app.current_org', $1, true)
08:16:35 INFO     sqlalchemy.engine.Engine  SELECT set_config('app.current_org', $1, true)
2026-06-20 08:16:35,069 INFO sqlalchemy.engine.Engine [cached since 370s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
08:16:35 INFO     sqlalchemy.engine.Engine  [cached since 370s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
2026-06-20 08:16:35,076 INFO sqlalchemy.engine.Engine INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
08:16:35 INFO     sqlalchemy.engine.Engine  INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
2026-06-20 08:16:35,076 INFO sqlalchemy.engine.Engine [cached since 367.2s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 43, 'consensus_update', '{"mean_confidence": 0.5333333333333333, "converged": false, "ranking": ["f8643676-2a92-4598-bd98-b8b172290d14:1", "3c80dd36-7b1e-4104-8d70-a224c3b048 ... (26 characters truncated) ... -8f8c-4f33ae8d01cf:1", "d5c89f32-433b-46a4-a516-425bd9bcd757:1", "73069a2f-5299-4e09-be89-bf1a462f2631:1", "1016f4ec-c4ea-4744-bee8-0cfbf5963320:1"]}', datetime.datetime(2026, 6, 20, 2, 46, 35, 65674, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
08:16:35 INFO     sqlalchemy.engine.Engine  [cached since 367.2s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 43, 'consensus_update', '{"mean_confidence": 0.5333333333333333, "converged": false, "ranking": ["f8643676-2a92-4598-bd98-b8b172290d14:1", "3c80dd36-7b1e-4104-8d70-a224c3b048 ... (26 characters truncated) ... -8f8c-4f33ae8d01cf:1", "d5c89f32-433b-46a4-a516-425bd9bcd757:1", "73069a2f-5299-4e09-be89-bf1a462f2631:1", "1016f4ec-c4ea-4744-bee8-0cfbf5963320:1"]}', datetime.datetime(2026, 6, 20, 2, 46, 35, 65674, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
2026-06-20 08:16:35,081 INFO sqlalchemy.engine.Engine COMMIT
08:16:35 INFO     sqlalchemy.engine.Engine  COMMIT
INFO:     Waiting for application shutdown.
2026-06-20 08:16:35,267 INFO sqlalchemy.engine.Engine BEGIN (implicit)
08:16:35 INFO     sqlalchemy.engine.Engine  BEGIN (implicit)
2026-06-20 08:16:35,267 INFO sqlalchemy.engine.Engine SELECT set_config('app.current_org', $1, true)
08:16:35 INFO     sqlalchemy.engine.Engine  SELECT set_config('app.current_org', $1, true)
2026-06-20 08:16:35,267 INFO sqlalchemy.engine.Engine [cached since 370.2s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
08:16:35 INFO     sqlalchemy.engine.Engine  [cached since 370.2s ago] ('093bdf94-5180-4579-bdc8-ca68145f08b5',)
2026-06-20 08:16:35,272 INFO sqlalchemy.engine.Engine INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
08:16:35 INFO     sqlalchemy.engine.Engine  INSERT INTO run_events (run_id, seq, type, data, ts, org_id) VALUES ($1::UUID, $2::BIGINT, $3::VARCHAR, $4::JSONB, $5::TIMESTAMP WITH TIME ZONE, $6::UUID) RETURNING run_events.id
2026-06-20 08:16:35,272 INFO sqlalchemy.engine.Engine [cached since 367.4s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 44, 'hitl_request', '{"candidate": "Verdict: HOLD\\n\\nTop 3 Conditions for Reevaluation:\\n1. Account Takeover Prevention: Implement multi-factor authentication (MFA) an ... (1523 characters truncated) ... 2f-5299-4e09-be89-bf1a462f2631:1", "1016f4ec-c4ea-4744-bee8-0cfbf5963320:1"], "converged": false, "allowed_decisions": ["approve", "edit", "reject"]}', datetime.datetime(2026, 6, 20, 2, 46, 35, 261183, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
08:16:35 INFO     sqlalchemy.engine.Engine  [cached since 367.4s ago] (UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'), 44, 'hitl_request', '{"candidate": "Verdict: HOLD\\n\\nTop 3 Conditions for Reevaluation:\\n1. Account Takeover Prevention: Implement multi-factor authentication (MFA) an ... (1523 characters truncated) ... 2f-5299-4e09-be89-bf1a462f2631:1", "1016f4ec-c4ea-4744-bee8-0cfbf5963320:1"], "converged": false, "allowed_decisions": ["approve", "edit", "reject"]}', datetime.datetime(2026, 6, 20, 2, 46, 35, 261183, tzinfo=datetime.timezone.utc), UUID('093bdf94-5180-4579-bdc8-ca68145f08b5'))
2026-06-20 08:16:35,277 INFO sqlalchemy.engine.Engine COMMIT
08:16:35 INFO     sqlalchemy.engine.Engine  COMMIT
2026-06-20 08:16:35,285 INFO sqlalchemy.engine.Engine UPDATE runs SET rounds=$1::INTEGER, status=$2::VARCHAR WHERE runs.id = $3::UUID
08:16:35 INFO     sqlalchemy.engine.Engine  UPDATE runs SET rounds=$1::INTEGER, status=$2::VARCHAR WHERE runs.id = $3::UUID
2026-06-20 08:16:35,285 INFO sqlalchemy.engine.Engine [generated in 0.00078s] (2, 'paused', UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'))
08:16:35 INFO     sqlalchemy.engine.Engine  [generated in 0.00078s] (2, 'paused', UUID('706be154-ef75-4976-93f6-d9da8b09fd7b'))
2026-06-20 08:16:35,298 INFO sqlalchemy.engine.Engine COMMIT
08:16:35 INFO     sqlalchemy.engine.Engine  COMMIT
2026-06-20 08:16:35,307 INFO sqlalchemy.engine.Engine BEGIN (implicit)
08:16:35 INFO     sqlalchemy.engine.Engine  BEGIN (implicit)
2026-06-20 08:16:35,309 INFO sqlalchemy.engine.Engine RESET app.current_org
08:16:35 INFO     sqlalchemy.engine.Engine  RESET app.current_org
2026-06-20 08:16:35,309 INFO sqlalchemy.engine.Engine [cached since 2163s ago] ()
08:16:35 INFO     sqlalchemy.engine.Engine  [cached since 2163s ago] ()
2026-06-20 08:16:35,314 INFO sqlalchemy.engine.Engine COMMIT
08:16:35 INFO     sqlalchemy.engine.Engine  COMMIT
08:16:35 INFO     backend.app.main  NEX AGI backend shut down
INFO:     Application shutdown complete.
INFO:     Finished server process [308316]
INFO:     Stopping reloader process [370572]