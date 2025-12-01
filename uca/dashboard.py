import streamlit as st
import json
import os
import pandas as pd
import plotly.graph_objects as go
import matplotlib.pyplot as plt
from wordcloud import WordCloud, STOPWORDS
import re
import sys

# Add parent directory to path to import UCA modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from uca.core import UCAEngine
from uca.constants import AgentMode
from uca.modules.network_analyzer import NetworkAnalyzer
import streamlit.components.v1 as components
from pyvis.network import Network
import tempfile

# Page Config
st.set_page_config(
    page_title="UCA Intelligence Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constants
JSON_FILE = "uca_results.json"

# Custom CSS - Notion Style (Light Mode)
st.markdown("""
<style>
    /* Notion-like Font & Background */
    .stApp {
        background-color: #FFFFFF; /* Light Mode */
        color: #37352F;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif, "Segoe UI Emoji", "Segoe UI Symbol";
    }
    
    /* Callout Block */
    .notion-callout {
        padding: 16px;
        border-radius: 4px;
        background-color: #F1F1EF; /* Light Gray */
        border: 1px solid #E1E1E0;
        margin-bottom: 16px;
        display: flex;
        align-items: flex-start;
        color: #37352F;
    }
    .notion-callout-icon {
        font-size: 24px;
        margin-right: 12px;
    }
    .notion-callout-content {
        color: #37352F;
    }
    
    /* Gallery Card */
    .gallery-card {
        background-color: #FFFFFF;
        border: 1px solid #E1E1E0;
        border-radius: 6px;
        box-shadow: rgba(15, 15, 15, 0.05) 0px 0px 0px 1px, rgba(15, 15, 15, 0.1) 0px 2px 4px;
        overflow: hidden;
        transition: background 100ms ease-out;
        margin-bottom: 20px;
        height: 100%;
    }
    .gallery-card:hover {
        background-color: #F7F7F5;
    }
    .gallery-card-content {
        padding: 12px;
    }
    .gallery-title {
        font-weight: 600;
        font-size: 16px;
        margin-bottom: 4px;
        color: #37352F;
    }
    .gallery-subtitle {
        font-size: 14px;
        color: #787774;
        margin-bottom: 8px;
    }
    
    /* Tags */
    .notion-tag {
        display: inline-block;
        padding: 0px 6px;
        border-radius: 4px;
        font-size: 12px;
        line-height: 20px;
        margin-right: 6px;
        font-weight: 500;
    }
    .tag-red { background: rgba(255, 100, 100, 0.1); color: #D44C47; }
    .tag-green { background: rgba(100, 255, 100, 0.1); color: #448361; }
    .tag-blue { background: rgba(100, 100, 255, 0.1); color: #2977C4; }
    .tag-gray { background: rgba(200, 200, 200, 0.3); color: #787774; }
</style>
""", unsafe_allow_html=True)

def render_callout(icon, title, content, color="gray"):
    st.markdown(f"""
    <div class="notion-callout">
        <div class="notion-callout-icon">{icon}</div>
        <div class="notion-callout-content">
            <strong>{title}</strong><br>
            {content}
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_gallery_card(title, category, description, price):
    st.markdown(f"""
    <div class="gallery-card">
        <div class="gallery-card-content">
            <div class="gallery-title">{title}</div>
            <div class="gallery-subtitle">
                <span class="notion-tag tag-green">{category}</span>
                <span class="notion-tag tag-gray">{price}</span>
            </div>
            <div style="font-size: 14px; color: #37352F;">{description}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def load_data():
    if not os.path.exists(JSON_FILE):
        return []
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return []

def plot_gauge(value, title, max_val=10):
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = value,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': title, 'font': {'color': '#37352F'}},
        gauge = {
            'axis': {'range': [None, max_val], 'tickwidth': 1, 'tickcolor': "#37352F"},
            'bar': {'color': "#00CC96"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "#E1E1E0",
            'steps': [
                {'range': [0, max_val*0.3], 'color': '#D44C47'},
                {'range': [max_val*0.3, max_val*0.7], 'color': '#F2C94C'},
                {'range': [max_val*0.7, max_val], 'color': '#00CC96'}],
        }))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor='rgba(0,0,0,0)', font={'color': '#37352F'})
    return fig

def generate_wordcloud(text):
    if not text:
        return None
    
    # Strip HTML tags
    text_clean = re.sub(r'<[^>]+>', '', text)
    # Remove URLs
    text_clean = re.sub(r'http\S+|www.\S+', '', text_clean)
    # Remove special characters but keep letters and spaces
    text_clean = re.sub(r'[^\w\sЀ-ӿ]', ' ', text_clean)
    
    if not text_clean.strip():
        return None
    
    # Use stopwords for English (and could add Russian)
    stopwords = set(STOPWORDS)
    stopwords.update(['alt', 'src', 'href', 'class', 'style', 'post', 'appeared', 'first'])
    
    wordcloud = WordCloud(
        width=800, 
        height=400, 
        background_color='white', # Light Mode
        colormap='viridis',
        stopwords=stopwords,
        collocations=False,
        min_font_size=10
    ).generate(text_clean)
    
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.imshow(wordcloud, interpolation='bilinear')
    ax.axis('off')
    plt.close(fig)
    return fig

def main():
    st.title("🧠 UCA Intelligence Dashboard")
    st.caption("Universal Commercial Agent • News-to-Cash Pipeline • GPT-5.1 Powered")

    # Load Data
    data = load_data()
    
    if not data:
        st.warning("No analysis results found. Run 'run_on_db.py' to generate data.")
        if st.button("Run Analysis Now"):
            with st.spinner("Running UCA Analysis..."):
                os.system("python uca/run_on_db.py")
                st.rerun()
        return

    # Sidebar
    st.sidebar.header("Select Analysis")
    options = [f"{item['original_article']['id']}: {item['original_article']['title'][:40]}..." for item in data]
    selected_option = st.sidebar.selectbox("Choose Article", options)
    
    st.sidebar.divider()
    
    # Time Range Selector
    time_range = st.sidebar.selectbox(
        "Select Time Range",
        ["Last 24 Hours", "Last 15 Days", "Last 30 Days"],
        index=0
    )
    
    days_map = {
        "Last 24 Hours": 1,
        "Last 15 Days": 15,
        "Last 30 Days": 30
    }
    
    if st.sidebar.button("🚀 Run New Analysis"):
        days = days_map[time_range]
        with st.spinner(f"Running UCA Analysis for {time_range}..."):
            try:
                # Initialize Engine
                uca = UCAEngine(mode=AgentMode.STORE_OWNER)
                # Run Analysis (Limit 5 to avoid long waits)
                results = uca.process_recent_news(limit=5, days=days)
                
                if not results:
                    st.warning("No articles found in this time range.")
                else:
                    # Save results
                    with open(JSON_FILE, "w", encoding="utf-8") as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                    st.success(f"Analysis Complete! Processed {len(results)} articles.")
                    st.rerun()
            except Exception as e:
                st.error(f"Analysis Failed: {e}")

    # Find selected item
    selected_index = options.index(selected_option)
    item = data[selected_index]
    orig = item['original_article']
    trend = item['trend_analysis']
    
    # --- Main Content ---
    
    # Header
    st.header(orig['title'])
    st.markdown(f"**Source ID:** `{orig['id']}` • **URL:** [{orig['url']}]({orig['url']})")
    
    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Overview", "📝 Text Analysis", "🕸️ Network", "💡 Products", "📢 Marketing"])
    
    # TAB 1: OVERVIEW
    with tab1:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Key Metrics")
            st.plotly_chart(plot_gauge(trend['velocity_score'], "Velocity", 10), use_container_width=True)
            st.plotly_chart(plot_gauge(trend['commercial_viability_score'] * 10, "Viability", 10), use_container_width=True)
            
        with col2:
            st.subheader("Insights")
            render_callout("🌊", "Lifecycle Stage", trend['lifecycle_stage'])
            
            emotions_str = ", ".join([f"<span class='notion-tag tag-red'>{e}</span>" for e in trend['dominant_emotions']])
            render_callout("❤️", "Dominant Emotions", emotions_str)
            
            psych = trend['empathy_map']
            with st.expander("🧠 Psychological Profile (Empathy Map)", expanded=True):
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**THINK**\n> {psych['think']}")
                    st.markdown(f"**FEEL**\n> {psych['feel']}")
                with c2:
                    st.markdown(f"**SAY**\n> {psych['say']}")
                    st.markdown(f"**DO**\n> {psych['do']}")

    # TAB 2: TEXT ANALYSIS
    with tab2:
        st.subheader("Article Word Cloud")
        # Combine title and content for better context
        full_text = f"{orig['title']} {orig.get('content', '')}"
        if full_text.strip():
            fig = generate_wordcloud(full_text)
            if fig:
                st.pyplot(fig)
            else:
                st.warning("Not enough text to generate Word Cloud.")
        else:
            st.warning("No article content available for Word Cloud.")
            
        st.divider()
        st.subheader("Full Text")
        with st.expander("Read Article Content"):
            st.write(orig.get('content', 'No content available.'))

    # TAB 3: NETWORK ANALYSIS
    with tab3:
        st.subheader("Text Network Graph (InfraNodus Style)")
        st.caption("Visualizing relationships between words to identify main topics and structural gaps.")
        
        full_text = f"{orig['title']} {orig.get('content', '')}"
        
        if full_text.strip():
            # Analyze
            analyzer = NetworkAnalyzer(window_size=4, min_edge_weight=2)
            net_data = analyzer.analyze(full_text)
            
            if net_data['nodes']:
                # Create PyVis Network
                net = Network(height="500px", width="100%", bgcolor="#ffffff", font_color="#333333", notebook=False)
                
                # Add nodes and edges
                for node in net_data['nodes']:
                    net.add_node(node['id'], label=node['label'], value=node['value'], title=node['title'], group=node['group'])
                
                for edge in net_data['edges']:
                    net.add_edge(edge['from'], edge['to'], value=edge['value'])
                
                # Physics options for better layout
                net.force_atlas_2based()
                
                # Save and display
                with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
                    net.save_graph(tmp.name)
                    tmp.seek(0)
                    html_content = tmp.read().decode('utf-8')
                    
                components.html(html_content, height=520)
                
                # Analysis Columns
                col_topics, col_insights = st.columns([1, 1])
                
                with col_topics:
                    st.subheader("Detected Topics")
                    communities = net_data['communities']
                    # Group words by community
                    topics = {}
                    for word, group in communities.items():
                        if group not in topics:
                            topics[group] = []
                        topics[group].append(word)
                    
                    for i, (group, words) in enumerate(topics.items()):
                        top_words = sorted(words, key=lambda w: net_data['graph_object'].degree(w), reverse=True)[:5]
                        st.markdown(f"**Topic {group + 1}**")
                        st.write(", ".join(top_words))

                with col_insights:
                    st.subheader("Structural Insights")
                    
                    # Influential Terms (Betweenness)
                    st.markdown("#### 🌉 Influential Terms (Brokers)")
                    st.caption("Words that connect different topics.")
                    centrality = net_data['centrality']
                    top_brokers = sorted(centrality.items(), key=lambda x: x[1], reverse=True)[:5]
                    for word, score in top_brokers:
                        st.markdown(f"- **{word}** ({score:.3f})")
                        
                    # Structural Gaps
                    st.markdown("#### 🚀 Innovation Opportunities (Gaps)")
                    st.caption("Disconnected concepts. Bridge them to create novelty.")
                    gaps = net_data['structural_gaps']
                    if gaps:
                        for gap in gaps:
                            st.info(f"**{gap['node_a']}** (Topic {gap['topic_a']})  ⚡  **{gap['node_b']}** (Topic {gap['topic_b']})")
                    else:
                        st.success("The discourse is well-connected. No major gaps found.")

                # AI Graph Insights (GraphRAG)
                st.divider()
                if st.button("✨ Generate AI Insights (GraphRAG)"):
                    with st.spinner("Analyzing graph structure with AI..."):
                        try:
                            uca_engine = UCAEngine(mode=AgentMode.STORE_OWNER)
                            insights = uca_engine.generate_graph_insights(net_data)
                            st.markdown("### 🧠 AI Network Analysis")
                            st.markdown(insights)
                        except Exception as e:
                            st.error(f"Failed to generate insights: {e}")
            else:
                st.warning("Not enough data to build a network graph.")
        else:
            st.warning("No text available for analysis.")

    # TAB 4: PRODUCTS
    with tab4:
        st.subheader("Commercial Opportunities")
        products = item['commercial_opportunities']
        
        # Grid Layout for Gallery
        cols = st.columns(2)
        for i, prod in enumerate(products):
            with cols[i % 2]:
                render_gallery_card(
                    title=prod['product_title'],
                    category=prod['category_id'],
                    description=prod['description'],
                    price=prod.get('price_point_suggestion', 'N/A')
                )
                
                if prod.get('visual_prompt'):
                    with st.expander("🎨 Visual Prompt"):
                        vp = prod['visual_prompt']
                        st.code(f"{vp['prompt']} {vp['aspect_ratio']}", language="text")

    # TAB 5: MARKETING
    with tab5:
        marketing = item.get('marketing_assets')
        if marketing:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("#### 📱 TikTok Campaign")
                tiktok = marketing['tiktok_campaign']
                st.write(f"**Hook:** {tiktok['hook_type']}")
                st.code(tiktok['caption'], language="text")
                st.write("**Hashtags:**")
                st.write(", ".join([f"`{tag}`" for tag in tiktok['hashtags']]))
                
            with col2:
                st.markdown("#### 🔍 SEO Keywords")
                seo = marketing['seo_tags']
                
                st.write("**Amazon KDP:**")
                # Visualize as horizontal bar chart of keywords (mock frequency) or just list
                st.write(", ".join([f"`{tag}`" for tag in seo['amazon_kdp']]))
                
                st.write("**Etsy:**")
                st.write(", ".join([f"`{tag}`" for tag in seo['etsy']]))
        else:
            st.info("No marketing assets generated.")

if __name__ == "__main__":
    main()
