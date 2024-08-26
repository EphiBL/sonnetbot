from sqlite3 import connect

class BotServerState():
    def __init__(self, guild):
        self.guild = guild
        self.active_thread_ids = []
        self.response_channel_id = self.load_response_channel_id()
        self.has_api_key = False
        self.has_set_response_channel = self.response_channel_id != 0 

    def get_servers(self):
        return self.active_servers
    
    def add_active_thread(self, thread):
        self.active_thread_ids.append(thread)

    def remove_active_thread(self, thread):
        self.active_thread_ids.remove(thread)

    def update_response_channel(self, id):
        self.response_channel_id = id


    def load_response_channel_id(self):
        conn = connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('SELECT response_channel_id FROM server_settings WHERE guild_id = ?', (self.guild.id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0

    def update_response_channel(self, id):
        self.response_channel_id = id
        conn = connect('bot_data.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO server_settings (guild_id, response_channel_id)
            VALUES (?, ?)
        ''', (self.guild.id, id))
        conn.commit()
        conn.close()
        self.has_set_response_channel = True

    def __repr__(self):
        return f'BotServerState:  Servers {self.guild}, Active Threads {self.active_thread_ids}'

# class AppState():
#     def __init__(self):
