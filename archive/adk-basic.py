#!/usr/bin/env python
# coding: utf-8

# # Lesson 3 - Introduction to Google's ADK - Part I

# In this lesson, you will familiarize yourself with Google's Agent Development Kit (ADK) that you will use in the next lessons to build your multi-agent system.
# 
# You'll learn:
# - how to create and run an agent using ADK (Part I)
# - how to create a team of Agents consisting of a root agent and 2 sub-agents (Part II)
# - how the team of agents can access a sharable context (Part II)
# 
# For each agent, you'll define a tool that allows the agent to interact with the Neo4j database we setup for this course. 
# 

# ## 3.1. Setup

# In[ ]:


# Import necessary libraries
import os
from google.adk.agents import Agent
from google.adk.models.lite_llm import LiteLlm # For OpenAI support
from google.adk.sessions import InMemorySessionService
from google.adk.runners import Runner
from google.genai import types # For creating message Content/Parts
from typing import Optional, Dict, Any

import warnings
warnings.filterwarnings("ignore")

import logging
logging.basicConfig(level=logging.CRITICAL)

print("Libraries imported.")


# In[ ]:


# Define Model Constants for easier use 
MODEL_GPT = "openai/gpt-4o"

llm = LiteLlm(model=MODEL_GPT)

# Test LLM with a direct call
print(llm.llm_client.completion(model=llm.model, 
                                messages=[{"role": "user", 
                                           "content": "Are you ready?"}], 
                                tools=[]))

print("\nOpenAI is ready for use.")


# ## 3.2. Explore `neo4j_for_adk`

# In your lab environment, you are provided with a graph database that your agent will interact with. For that, you are provided with a helper called `neo4j_for_adk` from which you'll import the instance `graphdb`, which wraps the Neo4j Python driver to make it ADK friendly.

# In[ ]:


# Convenience libraries for working with Neo4j inside of Google ADK
from neo4j_for_adk import graphdb


# <div style="background-color:#fff6ff; padding:13px; border-width:3px; border-color:#efe6ef; border-style:solid; border-radius:6px">
# <p> 💻 &nbsp; <b>To access neo4j_for_adk.py </b> 1) click on the <em>"File"</em> option on the top menu of the notebook and then 2) click on <em>"Open"</em>.
# 
# </div>

# `graphdb` has a method `send_query` which expects a cypher query, runs the query and then formats the results as follows:
# 
# <img src="images/send_query_expln.png" alt="diagram of the send_query method from the graphdb module showing success or failure response to a query" width=400>  

# In[ ]:


# Sending a simple query to the database
neo4j_is_ready = graphdb.send_query("RETURN 'Neo4j is Ready!' as message")

print(neo4j_is_ready)


# **Optional Note**: Neo4j Database Setup
# 
# We set up the database as a sidecar container. You can find the Docker installation instructions (and others) [here](https://neo4j.com/docs/operations-manual/current/docker/introduction/). We configured the username and password as part of the database setup. We also installed a plugin called [APOC](https://neo4j.com/labs/apoc/) (which will be needed in the last notebook). We defined these environment variables, which are used by `neo4j_for_adk.py`:
# - `NEO4J_URI="bolt://localhost:7687"`
# - `NEO4J_USERNAME="your_database_username"`
# - `NEO4J_PASSWORD="your_database_password"`

# ## 3.3. Define your Agent's Tool

# In[ ]:


# Define a basic tool -- send a parameterized cypher query
def say_hello(person_name: str) -> dict:
    """Formats a welcome message to a named person. 

    Args:
        person_name (str): the name of the person saying hello

    Returns:
        dict: A dictionary containing the results of the query.
              Includes a 'status' key ('success' or 'error').
              If 'success', includes a 'query_result' key with an array of result rows.
              If 'error', includes an 'error_message' key.
    """
    return graphdb.send_query("RETURN 'Hello to you, ' + $person_name AS reply",
    {
        "person_name": person_name
    })


# In[ ]:


# Example tool usage (optional test)
print(say_hello("ABK"))


# In[ ]:


# Example tool usage (optional test)
print(say_hello("RETURN 'injection attack avoided'"))


# ## 3.4. Define the Agent `friendly_cypher_agent`

# **Optional Reading**
# 
# - An `Agent` in Google ADK orchestrates the interaction between the user, the LLM, and the available tools
# 
# - you configure it with several key parameters:
#     * `name`: A unique identifier for this agent (e.g., "friendly_cypher_agent\_v1").  
#     * `model`: Specifies which LLM to use. you'll use the `llm` variable we defined above.  
#     * `description`: A summary of the agent's overall purpose. This is like public documentation that helps other agents decide when to delegate tasks to *this* agent.  
#     * `instruction`: Detailed guidance given to the LLM on how this agent should behave, its persona, goals, and specifically *how and when* to utilize its assigned `tools`.  
#     * `tools`: A list containing the actual Python tool functions the agent is allowed to use (e.g., `[say_hello]`).
# 
# **Best Practice:** 
# - Provide clear and specific `instruction` prompts. The more detailed the instructions, the better the LLM can understand its role and how to use its tools effectively. Be explicit about error handling if needed.
# - Choose descriptive `name` and `description` values. These are used internally by ADK and are vital for features like automatic delegation (covered later).

# In[ ]:


# Define the Cypher Agent
hello_agent = Agent(
    name="hello_agent_v1",
    model=llm, # defined earlier in a variable
    description="Has friendly chats with a user.",
    instruction="""You are a helpful assistant, chatting with a user. 
                Be polite and friendly, introducing yourself and asking who the user is. 

                If the user provides their name, use the 'say_hello' tool to get a custom greeting.
                If the tool returns an error, inform the user politely. 
                If the tool is successful, present the reply.
                """,
    tools=[say_hello], # Pass the function directly
)

print(f"Agent '{hello_agent.name}' created.")


# ## 3.5. Run the Agent

# To run an agent, you'll need some additional components namely an execution environment and memory.
# 

# ### 3.5.1. Event Loop   

# <img src="images/event_loop_3.png"  alt="diagram of Agent Development Kit runtime showing the Runner component handling an Event Loop with Services for the User" width=400> 
# 
# The [ADK Runtime](https://google.github.io/adk-docs/runtime/) orchestrates agents throughout execution. The main component is an event-driven loop intermediated by a Runner. When the runner receives a user query, it asks the agent to start processing. The agent processes the query and emits an event. The Runner receives the event, records state changes, updates memory and forwards the event to the user interface. After that, the agent's logic resumes and the cycle repeats until no further events are produced by the agent and the user has a response.

# ### 3.5.2. Create the Runner and SessionService

# Let's assume we have a single user talking to the agent in a single session. Let's create this user, the session and the runner:
# * `SessionService`: Responsible for managing conversation history and state for different users and sessions. The `InMemorySessionService` is a simple implementation that stores everything in memory, suitable for testing and simple applications. It keeps track of the messages exchanged.  
# * `Runner`: The engine that orchestrates the interaction flow. It takes user input, routes it to the appropriate agent, manages calls to the LLM and tools based on the agent's logic, handles session updates via the `SessionService`, and yields events representing the progress of the interaction.

# In[ ]:


app_name = hello_agent.name + "_app"
user_id = hello_agent.name + "_user"
session_id = hello_agent.name + "_session_01"
    
# Initialize a session service and a session
session_service = InMemorySessionService()
await session_service.create_session(
    app_name=app_name,
    user_id=user_id,
    session_id=session_id
)
    
runner = Runner(
    agent=hello_agent,
    app_name=app_name,
    session_service=session_service
)


# ### 3.5.3. Run the Agent

# Here's what's happening:
#  
# 1. Package the user query into the ADK `Content` format.
# 2. Call`runner.run_async` (providing it with user/session context and the new message)
# 4. Iterate through the **Events** yielded by the runner. Events represent steps in the agent's execution (e.g., tool call requested, tool result received, intermediate LLM thought, final response).  
# 5. Identify and print the **final response** event using `event.is_final_response()`.
# 
# **Why `async`?** Interactions with LLMs and potentially tools (like external APIs) are I/O-bound operations. Using `asyncio` allows the program to handle these operations efficiently without blocking execution.

# In[ ]:


user_message = "Hello, I'm ABK"
print(f"\n>>> User Message: {user_message}")

# Prepare the user's message in ADK format
content = types.Content(role='user', parts=[types.Part(text=user_message)])

final_response_text = "Agent did not produce a final response." # Default will be replaced if the agent produces a final response.


# We iterate through events to find the final answer.
verbose = False
async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
    if verbose:
        print(f"  [Event] Author: {event.author}, Type: {type(event).__name__}, Final: {event.is_final_response()}, Content: {event.content}")
    
    # Key Concept: is_final_response() marks the concluding message for the turn.
    if event.is_final_response():
        if event.content and event.content.parts:
            final_response_text = event.content.parts[0].text # Assuming text response in the first part
        elif event.actions and event.actions.escalate: # Handle potential errors/escalations
            final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
        break # Stop processing events once the final response is found

print(f"<<< Agent Response: {final_response_text}")


# ## 3.6. Create Helper Class: `AgentCaller`

# ### 3.6.1 Set up AgentCaller

# Let's wrap the runner in the helper class: `AgentCaller`. This helper will make it easier to make repeated calls to the agent by assuming we have a single user talking to the agent in a single session.

# In[ ]:


class AgentCaller:
    """A simple wrapper class for interacting with an ADK agent."""
    
    def __init__(self, agent: Agent, runner: Runner, 
                 user_id: str, session_id: str):
        """Initialize the AgentCaller with required components."""
        self.agent = agent
        self.runner = runner
        self.user_id = user_id
        self.session_id = session_id


    def get_session(self):
        return self.runner.session_service.get_session(app_name=self.runner.app_name, user_id=self.user_id, session_id=self.session_id)

    
    async def call(self, user_message: str, verbose: bool = False):
        """Call the agent with a query and return the response."""
        print(f"\n>>> User Message: {user_message}")

        # Prepare the user's message in ADK format
        content = types.Content(role='user', parts=[types.Part(text=user_message)])

        final_response_text = "Agent did not produce a final response." 
        
        # Key Concept: run_async executes the agent logic and yields Events.
        # We iterate through events to find the final answer.
        async for event in self.runner.run_async(user_id=self.user_id, session_id=self.session_id, new_message=content):
            # You can uncomment the line below to see *all* events during execution
            if verbose:
                print(f"  [Event] Author: {event.author}, Type: {type(event).__name__}, Final: {event.is_final_response()}, Content: {event.content}")

            # Key Concept: is_final_response() marks the concluding message for the turn.
            if event.is_final_response():
                if event.content and event.content.parts:
                    # Assuming text response in the first part
                    final_response_text = event.content.parts[0].text
                elif event.actions and event.actions.escalate: # Handle potential errors/escalations
                    final_response_text = f"Agent escalated: {event.error_message or 'No specific message.'}"
                break # Stop processing events once the final response is found

        print(f"<<< Agent Response: {final_response_text}")
        return final_response_text


# ### 3.6.2 Make an instance of the AgentCaller

# Rather than a class constructor, you'll use a factory method which needs to make some async calls to initialize the components (user_id, session_id and runner) before passing to them to the AgentCaller.
# 
# The factory method takes some parameters:
# 
# * `Agent`: the agent that we defined earlier
# * `initial_state`: optional initialization of the agent's "memory"
# 
# Inside, the method will create memory for the agent and a runner.
# 

# In[ ]:


async def make_agent_caller(agent: Agent, initial_state: Optional[Dict[str, Any]] = {}) -> AgentCaller:
    """Create and return an AgentCaller instance for the given agent."""
    app_name = agent.name + "_app"
    user_id = agent.name + "_user"
    session_id = agent.name + "_session_01"
    
    # Initialize a session service and a session
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        state=initial_state
    )
    
    runner = Runner(
        agent=agent,
        app_name=app_name,
        session_service=session_service
    )
    
    return AgentCaller(agent, runner, user_id, session_id)


# ### 3.6.3. Run the Conversation

# Now you can define an async function to run the conversation.

# In[ ]:


hello_agent_caller = await make_agent_caller(hello_agent)

# We need an async function to await our interaction helper
async def run_conversation():
    await hello_agent_caller.call("Hello I'm ABK")

    await hello_agent_caller.call("I am excited")

# Execute the conversation using await
await run_conversation()

