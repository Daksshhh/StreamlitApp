import streamlit as st
import pandas as pd
import sqlite3
from groq import Groq

# --- Load CSV and initialize SQLite ---
df = pd.read_csv("Synthetic_Email_Campaign_Data.csv")  # CSV must be in the same directory as app.py
conn = sqlite3.connect(':memory:')
df.to_sql("email_campaigns", conn, index=False, if_exists='replace')

# --- Setup Groq Client securely using secrets ---
groq_client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# --- Detect if LLM response contains SQL ---
def is_sql_query(text):
    sql_keywords = ("select", "with", "insert", "delete", "update")
    text_lower = text.strip().lower()
    return any(text_lower.startswith(kw) or f"\n{kw}" in text_lower for kw in sql_keywords)

# --- Extract SQL lines robustly ---
def extract_sql_from_text(text):
    lines = text.splitlines()
    sql_lines = [line.strip() for line in lines if any(
        line.strip().lower().startswith(kw)
        for kw in ("select", "with", "insert", "update", "delete", "from", "where", "order by", "group by", "limit")
    )]
    sql_query = " ".join(sql_lines).strip()
    if not sql_query.endswith(";"):
        sql_query += ";"
    return sql_query

def correct_grammar(prompt):
    correction_prompt = (
        f"Correct the grammar of this sentence without changing its meaning:\n\n'{prompt}'"
    )

    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that fixes grammar errors in prompts."},
            {"role": "user", "content": correction_prompt}
        ]
    )

    return response.choices[0].message.content.strip()

# --- Get Groq LLM response ---
def get_llm_response(prompt):
    system_prompt = (
        "You are a smart assistant. When asked a question that requires data analysis of the 'email_campaigns' table, "
    "respond ONLY with a valid and executable SQLite SQL query. Use only these columns:\n\n"
    "send_date, template_id, subject_line, pre_header_text, email_body, emails_sent, "
    "emails_unsubscribed, emails_clicked, emails_opened, sender_info\n\n"
    "✅ Important rules:\n"
    "- DO NOT leave commas dangling. Every SELECT must have properly formatted columns.\n"
    "- DO NOT mix explanation and SQL. Just return pure SQL only.\n"
    "- Always include SELECT and FROM clauses.\n"
    "- Use float division for any rate calculations. For example:\n"
    "  SUM(emails_clicked) * 1.0 / SUM(emails_sent) AS click_rate\n"
    "- GROUP BY subject_line or template_id when comparing performance.\n"
    "- Use ORDER BY DESC when showing best performing subject lines.\n\n"
    "📌 If the question is creative or non-analytical (like 'suggest ideas' or 'how to write a better email'), respond in plain English instead of SQL.\n"
    "Never respond with both SQL and explanation together."
    )

    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip()

# --- Execute SQL safely ---
def execute_sql_query(query):
    try:
        return pd.read_sql_query(query, conn)
    except Exception as e:
        return pd.DataFrame([{"error": str(e)}])

# --- Summarize SQL results ---
def summarize_results(prompt, result_df):
    if result_df.empty or "error" in result_df.columns:
        return "Sorry, I couldn't find a meaningful answer to your question."

    top_rows = result_df.head(5).to_dict(orient="records")
    summary_prompt = (
        f"Summarize the following SQL result in response to the user's question: '{prompt}'\n\n"
        f"Data: {top_rows}"
    )

    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": "You convert SQL table output into human-friendly summaries."},
            {"role": "user", "content": summary_prompt}
        ]
    )

    return response.choices[0].message.content.strip()

# --- Subject line improvement helper ---
def suggest_subject_line_improvement(subject_line):
    prompt = (
        f"The following email subject line had a very low open rate (~5%): '{subject_line}'.\n"
        "Give 3 specific improvements to make it more engaging and improve open rate."
    )

    response = groq_client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": "You improve poor email subject lines."},
            {"role": "user", "content": prompt}
        ]
    )

    return response.choices[0].message.content.strip()

# --- Streamlit UI ---
st.title("📬 Analytics Vidhya ChatBot")

user_input = st.text_input("Ask your question (e.g. campaign stats, advice, or tips):")

if user_input:
    with st.spinner("Thinking..."):
        corrected_input = correct_grammar(user_input)
        reply = get_llm_response(corrected_input)

        if is_sql_query(reply):
            sql_query = extract_sql_from_text(reply)
            st.markdown("### 🧾 SQL Query Generated")
            st.code(sql_query, language="sql")

            result = execute_sql_query(sql_query)

            if result.empty:
                st.warning("No results found for this query.")
            else:
                st.markdown("### 📊 Query Result")
                st.dataframe(result)

                summary = summarize_results(user_input, result)
                st.markdown("### 🧠 Summary")
                st.write(summary)
        else:
            st.markdown("### 🧠 Direct Answer")
            st.write(reply)

# --- Subject Line Analyzer ---
st.markdown("---")
st.subheader("✍️ Bad Subject Line? Get Suggestions")
subject_input = st.text_input("Paste a subject line with low open rate")

if subject_input:
    with st.spinner("Improving subject line..."):
        suggestions = suggest_subject_line_improvement(subject_input)
        st.markdown("### 📈 Suggestions")
        st.write(suggestions)
