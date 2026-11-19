// ==========================================================
// Business Central Agent - Frontend
// ==========================================================


// ==========================================================
// CONFIGURATION
// ==========================================================

const API_URL = "http://127.0.0.1:8000/chat";


// ==========================================================
// SESSION ID
// ==========================================================

// Each browser session gets its own conversation ID.
// This is important because your Python backend stores
// pending Sales Orders using session_id.

const sessionId =
    "web-" +
    Date.now() +
    "-" +
    Math.random()
        .toString(36)
        .substring(2, 9);


// ==========================================================
// DOM ELEMENTS
// ==========================================================

const chatForm =
    document.getElementById("chatForm");

const messageInput =
    document.getElementById("messageInput");

const sendButton =
    document.getElementById("sendButton");

const chatMessages =
    document.getElementById("chatMessages");

const typingIndicator =
    document.getElementById("typingIndicator");


// ==========================================================
// ADD MESSAGE TO CHAT
// ==========================================================

function addMessage(
    message,
    sender
) {

    const messageWrapper =
        document.createElement("div");

    messageWrapper.classList.add(
        "message"
    );


    // ------------------------------------------------------
    // AI message
    // ------------------------------------------------------

    if (sender === "ai") {

        messageWrapper.classList.add(
            "ai-message"
        );

        messageWrapper.innerHTML = `
            <div class="message-avatar">
                AI
            </div>

            <div class="message-content">

                <div class="message-name">
                    Business Central Agent
                </div>

                <div class="message-bubble"></div>

            </div>
        `;

    }

    // ------------------------------------------------------
    // User message
    // ------------------------------------------------------

    else {

        messageWrapper.classList.add(
            "user-message"
        );

        messageWrapper.innerHTML = `
            <div class="message-avatar">
                You
            </div>

            <div class="message-content">

                <div class="message-name">
                    You
                </div>

                <div class="message-bubble"></div>

            </div>
        `;
    }


    // ------------------------------------------------------
    // Put message text into bubble
    // ------------------------------------------------------

    const bubble =
        messageWrapper.querySelector(
            ".message-bubble"
        );

    bubble.textContent = message;


    // ------------------------------------------------------
    // Add to chat
    // ------------------------------------------------------

    chatMessages.appendChild(
        messageWrapper
    );


    // ------------------------------------------------------
    // Scroll to latest message
    // ------------------------------------------------------

    chatMessages.scrollTop =
        chatMessages.scrollHeight;
}


// ==========================================================
// SHOW TYPING INDICATOR
// ==========================================================

function showTyping() {

    typingIndicator.classList.remove(
        "hidden"
    );

    chatMessages.scrollTop =
        chatMessages.scrollHeight;
}


// ==========================================================
// HIDE TYPING INDICATOR
// ==========================================================

function hideTyping() {

    typingIndicator.classList.add(
        "hidden"
    );
}


// ==========================================================
// SEND MESSAGE TO FASTAPI
// ==========================================================

async function sendMessage(
    message
) {

    try {

        // --------------------------------------------------
        // Disable input while waiting
        // --------------------------------------------------

        sendButton.disabled = true;

        messageInput.disabled = true;

        showTyping();


        // --------------------------------------------------
        // Send request to FastAPI
        // --------------------------------------------------

        const response =
            await fetch(
                API_URL,
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({

                        message: message,

                        session_id:
                            sessionId

                    })
                }
            );


        // --------------------------------------------------
        // HTTP error
        // --------------------------------------------------

        if (!response.ok) {

            throw new Error(
                `Server returned ${response.status}`
            );
        }


        // --------------------------------------------------
        // Read response
        // --------------------------------------------------

        const data =
            await response.json();


        // --------------------------------------------------
        // Hide typing
        // --------------------------------------------------

        hideTyping();


        // --------------------------------------------------
        // Display AI response
        // --------------------------------------------------

        if (data.ai_response) {

            addMessage(
                data.ai_response,
                "ai"
            );

        }
        else {

            addMessage(
                "The agent returned an empty response.",
                "ai"
            );
        }

    }

    catch (error) {

        console.error(
            "Chat error:",
            error
        );

        hideTyping();


        // --------------------------------------------------
        // Display error
        // --------------------------------------------------

        addMessage(
            "I could not connect to the Business Central Agent. " +
            "Please make sure the FastAPI server is running.",
            "ai"
        );

    }

    finally {

        // --------------------------------------------------
        // Enable input again
        // --------------------------------------------------

        sendButton.disabled = false;

        messageInput.disabled = false;

        messageInput.focus();
    }
}


// ==========================================================
// FORM SUBMIT
// ==========================================================

chatForm.addEventListener(
    "submit",
    async function (event) {

        event.preventDefault();


        const message =
            messageInput.value.trim();


        // --------------------------------------------------
        // Ignore empty messages
        // --------------------------------------------------

        if (!message) {

            return;
        }


        // --------------------------------------------------
        // Display user message
        // --------------------------------------------------

        addMessage(
            message,
            "user"
        );


        // --------------------------------------------------
        // Clear input
        // --------------------------------------------------

        messageInput.value = "";


        // --------------------------------------------------
        // Send to backend
        // --------------------------------------------------

        await sendMessage(
            message
        );

    }
);


// ==========================================================
// ENTER KEY
// ==========================================================

messageInput.addEventListener(
    "keydown",
    function (event) {

        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {

            event.preventDefault();

            chatForm.requestSubmit();
        }

    }
);


// ==========================================================
// INITIAL FOCUS
// ==========================================================

messageInput.focus();