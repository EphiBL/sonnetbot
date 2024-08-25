class BotServerState():
    def __init__(self, guild_id):
        self.guild = guild_id
        self.active_thread_ids = []
        self.response_channel_id = 0 

    def get_servers(self):
        return self.active_servers
    
    def add_active_thread(self, thread):
        self.active_thread_ids.append(thread)

    def remove_active_thread(self, thread):
        self.active_thread_ids.remove(thread)

    def update_response_channel(self, id):
        self.response_channel_id = id

    def __repr__(self):
        return f'BotServerState: Active Servers {self.guild}, Active Threads {self.active_thread_ids}'
    


