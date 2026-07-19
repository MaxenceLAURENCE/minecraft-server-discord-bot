import os
import discord
from discord import app_commands
from discord.ext import commands
import docker
import requests
from mcstatus import JavaServer
import asyncio
from dotenv import load_dotenv

# Charger les variables d'environnement (.env)
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
CONTAINER_NAME = os.getenv("MINECRAFT_CONTAINER_NAME", "")
MINECRAFT_HOST = os.getenv("MINECRAFT_HOST", "")
MINECRAFT_PORT = int(os.getenv("MINECRAFT_PORT", "25565"))

class MinecraftBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        # Enregistre et synchronise les slash commands globalement
        await self.tree.sync()
        print("Command tree synced.")

bot = MinecraftBot()

def get_docker_client():
    try:
        return docker.from_env()
    except Exception as e:
        print(f"Error connecting to Docker daemon: {e}")
        return None

def get_local_ip():
    if MINECRAFT_HOST:
        return MINECRAFT_HOST
        
    # Détecter dynamiquement l'IP locale (LAN) de l'hôte via le démon Docker
    try:
        client = docker.from_env()
        # On lance un mini-conteneur temporaire en mode réseau 'host' pour lire l'IP LAN de l'hôte.
        # Comme l'image python:3.11-slim est déjà cachée (utilisée pour ce bot), c'est instantané.
        container = client.containers.run(
            "python:3.11-slim",
            "python -c \"import socket; s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(('8.8.8.8', 80)); print(s.getsockname()[0]); s.close()\"",
            network_mode="host",
            remove=True,
            stdout=True
        )
        ip = container.decode("utf-8").strip()
        if ip and not ip.startswith("127."):
            return ip
    except Exception as e:
        print(f"Détection dynamique de l'IP LAN de l'hôte en échec : {e}")

    return "localhost"


def check_container_state(container_name):
    client = get_docker_client()
    if not client:
        return "UNKNOWN", "Impossible de se connecter au démon Docker sur l'hôte."
    
    try:
        container = client.containers.get(container_name)
        return container.status, None
    except docker.errors.NotFound:
        return "NOT_FOUND", f"Le conteneur '{container_name}' n'existe pas."
    except Exception as e:
        return "ERROR", str(e)

@bot.event
async def on_ready():
    print(f"Bot connecté en tant que {bot.user.name}")
    await bot.change_presence(activity=discord.Game(name="/mcstatus"))

@bot.hybrid_command(name="mcstatus", description="Affiche l'état du serveur Minecraft (Docker et en jeu).")
async def mcstatus(ctx: commands.Context):
    await ctx.defer()
    
    status, err = check_container_state(CONTAINER_NAME)
    
    embed = discord.Embed(title="🎮 État du Serveur Minecraft", color=discord.Color.blue())
    
    if status == "running":
        embed.add_field(name="🐳 Conteneur Docker", value="🟢 En cours d'exécution (Running)", inline=False)
        
        ip = get_local_ip()
        embed.add_field(name="🔌 Adresse IP de connexion", value=f"`{ip}:{MINECRAFT_PORT}`", inline=False)
        
        try:
            # On interroge le serveur via l'IP locale (LAN) résolue de l'hôte
            server = JavaServer.lookup(f"{ip}:{MINECRAFT_PORT}")
            query = await server.async_status()
            
            embed.color = discord.Color.green()
            embed.add_field(name="🎮 Statut du jeu", value="🟢 En ligne / Prêt", inline=True)
            embed.add_field(name="👥 Joueurs", value=f"{query.players.online}/{query.players.max}", inline=True)
            embed.add_field(name="🏷️ Version", value=query.version.name, inline=True)
            if query.players.sample:
                players_list = ", ".join([p.name for p in query.players.sample])
                embed.add_field(name="👤 Liste des joueurs", value=players_list, inline=False)
                
        except Exception:
            # Si le conteneur tourne mais le serveur ne répond pas au ping, il charge (surtout avec des mods)
            embed.color = discord.Color.gold()
            embed.add_field(name="🎮 Statut du jeu", value="🟡 Démarrage en cours (le jeu s'initialise...)", inline=False)
            
    elif status in ["exited", "stopped"]:
        embed.color = discord.Color.red()
        embed.add_field(name="🐳 Conteneur Docker", value="🔴 Éteint (Stopped)", inline=False)
        embed.add_field(name="🎮 Statut du jeu", value="🔴 Hors ligne", inline=False)
    elif status == "NOT_FOUND":
        embed.color = discord.Color.red()
        embed.add_field(name="⚠️ Erreur Docker", value=err, inline=False)
    else:
        embed.color = discord.Color.dark_gray()
        embed.add_field(name="🐳 Conteneur Docker", value=f"⚪ Statut : {status}", inline=False)
        if err:
            embed.add_field(name="⚠️ Détails", value=err, inline=False)
            
    await ctx.send(embed=embed)

@bot.hybrid_command(name="mcstart", description="Démarre le conteneur du serveur Minecraft.")
async def mcstart(ctx: commands.Context):
    await ctx.defer()
    client = get_docker_client()
    if not client:
        await ctx.send("❌ Erreur : Impossible de se connecter au démon Docker.")
        return
        
    try:
        container = client.containers.get(CONTAINER_NAME)
        if container.status == "running":
            await ctx.send("🟢 Le serveur Minecraft est déjà démarré.")
            return
            
        await ctx.send("⏳ Démarrage du conteneur Minecraft...")
        container.start()
        
        await asyncio.sleep(3)
        container.reload()
        if container.status == "running":
            ip = get_local_ip()
            embed = discord.Embed(title="🟢 Serveur démarré !", color=discord.Color.green())
            embed.description = f"Le conteneur Docker a été lancé.\nAdresse : `{ip}:{MINECRAFT_PORT}`\n\n*Note : L'initialisation du jeu et des mods peut prendre 1 à 2 minutes.*"
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Statut anormal après démarrage : `{container.status}`")
            
    except docker.errors.NotFound:
        await ctx.send(f"❌ Erreur : Le conteneur '{CONTAINER_NAME}' n'existe pas.")
    except Exception as e:
        await ctx.send(f"❌ Une erreur est survenue lors du démarrage : `{e}`")

@bot.hybrid_command(name="mcstop", description="Arrête proprement le conteneur du serveur Minecraft.")
async def mcstop(ctx: commands.Context):
    await ctx.defer()
    client = get_docker_client()
    if not client:
        await ctx.send("❌ Erreur : Impossible de se connecter au démon Docker.")
        return
        
    try:
        container = client.containers.get(CONTAINER_NAME)
        if container.status != "running":
            await ctx.send("🔴 Le serveur Minecraft est déjà arrêté.")
            return
            
        await ctx.send("⏳ Arrêt du serveur Minecraft en cours (envoi du signal d'arrêt propre)...")
        # Stop proprement le conteneur (itzg/minecraft-server intercepte SIGTERM pour sauvegarder et éteindre proprement)
        container.stop(timeout=30)
        
        await asyncio.sleep(2)
        container.reload()
        if container.status != "running":
            await ctx.send("🔴 Le serveur Minecraft a été éteint.")
        else:
            await ctx.send("⚠️ Le conteneur n'a pas répondu à l'arrêt. Réessayez.")
            
    except docker.errors.NotFound:
        await ctx.send(f"❌ Erreur : Le conteneur '{CONTAINER_NAME}' n'existe pas.")
    except Exception as e:
        await ctx.send(f"❌ Une erreur est survenue lors de l'arrêt : `{e}`")

@bot.hybrid_command(name="mcrestart", description="Redémarre le conteneur du serveur Minecraft.")
async def mcrestart(ctx: commands.Context):
    await ctx.defer()
    client = get_docker_client()
    if not client:
        await ctx.send("❌ Erreur : Impossible de se connecter au démon Docker.")
        return
        
    try:
        container = client.containers.get(CONTAINER_NAME)
        await ctx.send("⏳ Redémarrage du serveur Minecraft...")
        container.restart(timeout=30)
        
        await asyncio.sleep(3)
        container.reload()
        if container.status == "running":
            ip = get_local_ip()
            embed = discord.Embed(title="🔄 Serveur redémarré !", color=discord.Color.green())
            embed.description = f"Le conteneur Docker a été redémarré.\nAdresse : `{ip}:{MINECRAFT_PORT}`\n\n*Note : L'initialisation du jeu et des mods peut prendre 1 à 2 minutes.*"
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ Statut anormal après redémarrage : `{container.status}`")
            
    except docker.errors.NotFound:
        await ctx.send(f"❌ Erreur : Le conteneur '{CONTAINER_NAME}' n'existe pas.")
    except Exception as e:
        await ctx.send(f"❌ Une erreur est survenue lors du redémarrage : `{e}`")

@bot.hybrid_command(name="mcip", description="Donne l'adresse IP de connexion du serveur.")
async def mcip(ctx: commands.Context):
    ip = get_local_ip()
    embed = discord.Embed(title="🔌 Connexion au Serveur", color=discord.Color.blue())
    embed.description = f"Pour vous connecter au serveur Minecraft, utilisez l'adresse IP suivante :\n\n📍 **`{ip}:{MINECRAFT_PORT}`**"
    await ctx.send(embed=embed)

if __name__ == "__main__":
    if not TOKEN:
        print("ERREUR : Le jeton DISCORD_TOKEN n'est pas configuré dans le fichier .env.")
    else:
        bot.run(TOKEN)
