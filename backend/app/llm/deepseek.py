"""Deepseek LLM integration."""
from typing import List, Dict, Optional, Callable, Any
import asyncio
import openai
from app.config import settings
import logging
import json

logger = logging.getLogger(__name__)


class DeepseekLLM:
    """Interface for Deepseek language model with function calling support."""
    
    def __init__(self):
        self.client = openai.OpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url
        )
        self.model = settings.deepseek_model
        self.tools = {}  # Store available tools
    
    def register_tool(self, name: str, description: str, parameters: Dict, func: Callable):
        """Register a tool/function that the LLM can call."""
        self.tools[name] = {
            'function': func,
            'description': description,
            'parameters': parameters
        }
    
    def get_tools_schema(self) -> List[Dict]:
        """Get OpenAI function calling schema for registered tools."""
        tools_schema = []
        for name, tool_info in self.tools.items():
            tools_schema.append({
                'type': 'function',
                'function': {
                    'name': name,
                    'description': tool_info['description'],
                    'parameters': tool_info['parameters']
                }
            })
        return tools_schema
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, use_tools: bool = False):
        """Send a chat completion request to Deepseek."""
        try:
            kwargs = {
                'model': self.model,
                'messages': messages,
                'temperature': temperature
            }
            
            if use_tools and self.tools:
                kwargs['tools'] = self.get_tools_schema()
                kwargs['tool_choice'] = 'auto'
            
            response = self.client.chat.completions.create(**kwargs)
            
            message = response.choices[0].message
            
            # Check if the model wants to call a function
            tool_calls = getattr(message, 'tool_calls', None)
            if tool_calls:
                return None, tool_calls
            
            return message.content or "", None
        except Exception as e:
            logger.error(f"Error calling Deepseek API: {e}")
            raise
    
    async def chat_with_tools(self, messages: List[Dict[str, str]], max_iterations: int = 5, collect_urls: Optional[List[str]] = None) -> str:
        """Chat with function calling support. Executes tool calls and returns final response.
        
        Args:
            messages: Conversation messages
            max_iterations: Maximum number of tool call iterations
            collect_urls: Optional list to collect source URLs from tool results
        """
        conversation = messages.copy()
        iteration = 0
        
        if collect_urls is None:
            collect_urls = []
        
        while iteration < max_iterations:
            iteration += 1
            
            # Call LLM
            content, tool_calls = self.chat(conversation, use_tools=True)
            
            # If we got a response (no tool calls), return it
            if content:
                return content
            
            # Execute tool calls
            if tool_calls:
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    logger.info(f"LLM calling tool: {function_name} with args: {function_args}")
                    
                    # Execute the function
                    if function_name in self.tools:
                        try:
                            func = self.tools[function_name]['function']
                            # Check if function is async
                            if asyncio.iscoroutinefunction(func):
                                result = await func(**function_args)
                            else:
                                result = func(**function_args)
                            
                                            # Add tool call and result to conversation
                            # Create assistant message with tool calls
                            assistant_msg = {
                                'role': 'assistant',
                                'content': None
                            }
                            # Add tool_calls if the API expects it
                            if hasattr(tool_call, 'id'):
                                assistant_msg['tool_calls'] = [{
                                    'id': tool_call.id,
                                    'type': 'function',
                                    'function': {
                                        'name': function_name,
                                        'arguments': tool_call.function.arguments
                                    }
                                }]
                            conversation.append(assistant_msg)
                            
                            # Extract URL from tool result if available
                            if isinstance(result, dict):
                                # Extract URL from result
                                url = result.get('url') or result.get('_source_url')
                                if url and url not in collect_urls:
                                    collect_urls.append(url)
                                    logger.info(f"📎 Collected source URL: {url}")
                                # Pretty format dict results for better readability
                                formatted_result = json.dumps(result, indent=2)
                            elif isinstance(result, list):
                                formatted_result = json.dumps(result, indent=2)
                                # Check if list contains dicts with URLs
                                for item in result:
                                    if isinstance(item, dict):
                                        url = item.get('url') or item.get('_source_url')
                                        if url and url not in collect_urls:
                                            collect_urls.append(url)
                            else:
                                formatted_result = str(result)
                            
                            tool_result = {
                                'role': 'tool',
                                'content': formatted_result
                            }
                            if hasattr(tool_call, 'id'):
                                tool_result['tool_call_id'] = tool_call.id
                            conversation.append(tool_result)
                        except Exception as e:
                            logger.error(f"Error executing tool {function_name}: {e}")
                            conversation.append({
                                'role': 'tool',
                                'tool_call_id': tool_call.id,
                                'content': f"Error: {str(e)}"
                            })
                    else:
                        logger.warning(f"Unknown tool: {function_name}")
                        conversation.append({
                            'role': 'tool',
                            'tool_call_id': tool_call.id,
                            'content': f"Error: Unknown tool {function_name}"
                        })
            else:
                break
        
        # If we exhausted iterations, return a message
        return "I apologize, but I encountered an issue processing your request. Please try again."
    
    def generate_with_context(
        self, 
        user_query: str, 
        context: List[Dict], 
        system_prompt: Optional[str] = None
    ) -> str:
        """Generate response with retrieved context."""
        if system_prompt is None:
            system_prompt = self._get_default_system_prompt()
        
        # Format context
        context_text = self._format_context(context)
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Context:\n{context_text}\n\nUser Question: {user_query}"}
        ]
        
        return self.chat(messages, temperature=0.3)
    
    def _format_context(self, context: List[Dict]) -> str:
        """Format context documents for the LLM."""
        formatted_parts = []
        for i, doc in enumerate(context, 1):
            metadata = doc.get('metadata', {})
            text = doc.get('text', '')
            
            part_info = f"[Document {i}]"
            if metadata.get('part_number'):
                part_info += f" Part Number: {metadata['part_number']}"
            if metadata.get('type'):
                part_info += f" Type: {metadata['type']}"
            
            formatted_parts.append(f"{part_info}\n{text}\n")
        
        return "\n".join(formatted_parts)
    
    def _get_default_system_prompt(self) -> str:
        """Get default system prompt for the chat agent."""
        return """You are a helpful assistant for PartSelect, an e-commerce website specializing in appliance parts, specifically Refrigerators and Dishwashers.

Your role is to:
1. Provide accurate product information based on part numbers
2. Check compatibility between parts and appliance models
3. Provide installation instructions and guidance
4. Help troubleshoot common issues with refrigerators and dishwashers

Important guidelines:
- Only answer questions related to refrigerator and dishwasher parts
- If asked about something outside this scope, politely decline and redirect to the relevant topic
- Base your answers on the provided context from the website
- If you don't have information in the context, say so honestly
- Be clear, concise, and helpful
- For installation questions, provide step-by-step guidance when available
- For compatibility questions, verify the specific model numbers mentioned

Always prioritize accuracy and user safety in your responses.

When answering questions about parts:
- Use the information provided in the context from the scraped website
- If the context contains installation instructions, provide them directly
- If the context contains appliance type information, use it in your response
- Do not ask the user for information that is already available in the context
- Provide complete, actionable answers based on the scraped data"""

