from typing import AsyncGenerator, Optional, List
from fastapi_poe.types import PartialResponse as BotMessage
import uuid
import time
import json


class PoeResponse:
    async def stream_response(self,
                              poe_bot_stream_partials: AsyncGenerator[BotMessage, None],
                              bot_name: str,
                              tools: list
                              ) -> AsyncGenerator[str, None]:
        response_template = {
            "id": str(uuid.uuid4()),
            "object": "chat.completion.chunk",
            "created": time.time(),
            "model": bot_name,
            "choices": [
                {
                    "index": 0,
                    "delta": {
                        "role": "assistant",
                        "content": ""
                    },
                    "logprobs": None,
                    "finish_reason": None,
                }
            ],
        }
        is_use_tool = False
        last_texts = ""  # Store last text for comparison
        
        async for partial in poe_bot_stream_partials:
            if len(tools) > 0 and partial.data is not None:
                is_use_tool = True
                #yield f"data: {json.dumps(partial.data, ensure_ascii=False)}\n\n"
            #else:
            current_text = partial.text
            if current_text.startswith("Searching ..."):
                continue
            if current_text.startswith("Generating image"):
                continue
            if current_text.startswith("Thinking..."):
                continue
            if partial.is_replace_response:
                # Shift texts in the buffer
                #last_three_texts = last_three_texts[1:] + [current_text]
                
                # Check if the texts are incrementally growing
                if len(last_texts)==0:
                    diff_text = current_text
                if (len(current_text) > len(last_texts) and
                    current_text.startswith(last_texts)):
                    # Output only the difference between the last two texts
                    diff_text = current_text[len(last_texts):]
                    if diff_text[-1].isdigit():
                        continue
                    response_template["choices"][0]["delta"]["content"] = diff_text
                    last_texts = current_text
                    yield f"data: {json.dumps(response_template)}\n\n"
                else:
                    continue
            else:
                last_texts += current_text
                response_template["choices"][0]["delta"]["content"] = current_text
                yield f"data: {json.dumps(response_template)}\n\n"

        if is_use_tool is False:
            response_template["choices"][0]["delta"] = {}
            response_template["choices"][0]["finish_reason"] = "stop"
            yield f"data: {json.dumps(response_template)}\n\ndata: [DONE]\n\n"
        else:
            yield f"data: [DONE]\n\n"

    async def not_stream_response(self,
                                  poe_bot_stream_partials: AsyncGenerator[BotMessage, None],
                                  bot_name: str,
                                  tools: list
                                  ) -> dict:
        def get_from_list(lst, index, default=None):
            return lst[index] if index < len(lst) else default

        response_template = {
            "id": str(uuid.uuid4()),
            "object": "chat.completion",
            "created": time.time(),
            "model": bot_name,
            "system_fingerprint": "fp_44709d6fcb",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "",
                    },
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 9, "completion_tokens": 12, "total_tokens": 21},
        }

        content = ""
        is_use_tool = False
        function_name = []
        arguments = []
        arguments_only_content = ""
        id = []
        last_replace_text = ""
        
        async for partial in poe_bot_stream_partials:
            if len(tools) > 0 and partial.data is not None:
                is_use_tool = True
                choices = get_from_list(partial.data.get("choices", []), 0, {})
                tool_calls = choices.get("delta", {}).get("tool_calls", [])
                function_content = get_from_list(tool_calls, 0, {}).get("function", {})
                tool_function_name = function_content.get("name", "")

                if tool_function_name != "":
                    function_name.append(tool_function_name)
                    if arguments_only_content != "":
                        arguments.append(arguments_only_content)
                        arguments_only_content = ""

                function_id = get_from_list(tool_calls, 0, {}).get("id", "")
                if function_id != "":
                    id.append(function_id)

                function_arguments = function_content.get("arguments", "")
                arguments_only_content += function_arguments
                item_content = choices.get("delta", {}).get("content", None)
                if item_content is not None:
                    content += item_content
            else:
                if partial.is_replace_response:
                    last_replace_text = partial.text
                    content = partial.text
                else:
                    if not last_replace_text:  # Only append if not in replace mode
                        content += partial.text

        if is_use_tool is False:
            response_template["choices"][0]["message"]["content"] = content
        else:
            arguments.append(arguments_only_content)
            tool_calls = []
            for i in range(len(id)):
                tool_calls.append({
                    "id": id[i],
                    "type": "function",
                    "function": {
                        "name": function_name[i],
                        "arguments": arguments[i]
                    }
                })
            response_template["choices"][0] = {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content if content != "" else None,
                    "tool_calls": tool_calls
                },
                "logprobs": None,
                "finish_reason": "tool_calls",
            }

        return response_template
