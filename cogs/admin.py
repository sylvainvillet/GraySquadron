import discord
from discord.ext import commands, tasks, menus
import datetime
from utils import helper, gonk_menus


# noinspection PyMethodMayBeStatic
class Admin(commands.Cog):

    def __init__(self, client):
        self.client = client
        self.update_nick.start()
        self.inactive.start()
        self.lt_increment = helper.get_config('lt_increment')

    def cog_unload(self):
        self.update_nick.cancel()
        self.inactive.cancel()
        helper.set_value('lt_increment', self.lt_increment)

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print('Cog is online.')

    @commands.Cog.listener()
    async def on_message(self, message):
        """Assign Cadet role after posting in introductions"""
        if message.author == self.client.user:
            return
        elif message.guild:
            if message.channel.name == 'introductions':
                if discord.utils.get(message.guild.roles, name='Citizen') in message.author.roles:
                    if len(message.content) > 10:
                        await message.author.add_roles(discord.utils.get(message.guild.roles, name='Cadet'))

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload):
        message = payload.cached_message
        if message.channel.name != 'bot-logs' and not message.content.startswith('$') and message.author.id != helper.get_config('bot_discord_uid'):
            em = discord.Embed(title='Message Deletion:', colour=0xff0000)
            em.add_field(name='Author', value='{0}'.format(message.author), inline=False)
            em.add_field(name='Channel', value='{0}'.format(message.channel), inline=False)
            em.add_field(name='Message', value=message.content, inline=False)
            em.set_footer(text='Deleted At: %s' % datetime.datetime.now())
            guild = self.client.get_guild(helper.get_config('guild_id'))
            log_channel = discord.utils.get(guild.text_channels, name='bot-logs')
            await log_channel.send(embed=em)

    # make a bool botvar, put conditional inside listener

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Assign citizen role on user join"""
        roles_list = ['Citizen', 'LFG', 'Active']
        for role in roles_list:
            role = discord.utils.get(member.guild.roles, name=role)
            await member.add_roles(role)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        """Remove lower rank when higher rank is granted and posts responsibilities"""
        guild = self.client.get_guild(helper.get_config('guild_id'))
        general_channel = discord.utils.get(guild.text_channels, name='general')
        if len(after.roles) > len(before.roles):
            new_role = next(role for role in after.roles if role not in before.roles)
            # if new_role.name == 'Citizen':
            #     intro_channel = discord.utils.get(guild.text_channels, name='introductions')
            #     await general_channel.send(f'Welcome to the GRAY SIDE {after.mention} please post in {intro_channel.mention}!')
            if new_role.name == 'Cadet':
                roles_channel = discord.utils.get(guild.text_channels, name='roles')
                rem_role = discord.utils.get(after.guild.roles, name='Citizen')
                await after.remove_roles(rem_role)
                await self.update_member_nick(None, after)
                await general_channel.send(f'{after.mention} has been promoted to {new_role}!\n'
                                           f'Select your roles in {roles_channel.mention}\n'
                                           f'Demonstrate good teamwork ability to get promoted to FO!')
                lt_list = discord.utils.get(after.guild.roles, name='Lieutenant').members
                retired_list = discord.utils.get(after.guild.roles, name='Retired').members
                active_lt_list = []
                for lt in lt_list:
                    if lt not in retired_list:
                        active_lt_list += [lt]
                if active_lt_list:
                    self.lt_increment = self.lt_increment + 1 if self.lt_increment < len(active_lt_list) - 1 else 0
                    await self.assign_mentor(None, active_lt_list[self.lt_increment], after)
                    await general_channel.send(
                        f'{after.mention} your assigned mentor is: {active_lt_list[self.lt_increment].mention}!')
                else:
                    await helper.bot_log(self.client, 'Error: All Lieutenants are retired!')
            elif new_role.name == 'Flight Officer':
                lft_channel = discord.utils.get(guild.text_channels, name='looking-for-team')
                ace_channel = discord.utils.get(guild.text_channels, name='ace-pilot-stats')
                roster_channel = discord.utils.get(guild.text_channels, name='roster')
                rem_role = discord.utils.get(after.guild.roles, name='Cadet')
                await after.remove_roles(rem_role)
                await self.update_member_nick(None, after)
                await self.clear_mentee(None, after)
                await general_channel.send(f'{after.mention} has been promoted to {new_role}!\n'
                                           f'You are now qualified to join a team! Message in {lft_channel.mention}\n'
                                           f'You can now request the Ace role in {ace_channel.mention}\n'
                                           f'You can now claim a FO number using $claim! See {roster_channel.mention}\n'
                                           f'Demonstrate leadership ability to get promoted to LT!')
            elif new_role.name == 'Lieutenant':
                roster_channel = discord.utils.get(guild.text_channels, name='roster')
                rem_role = discord.utils.get(after.guild.roles, name='Flight Officer')
                await after.remove_roles(rem_role)
                await self.update_member_nick(None, after)
                await general_channel.send(f'{after.mention} has been promoted to {new_role}!\n'
                                           f'Promotes Cadets to Flight Officers and tell them to choose a call sign in {roster_channel.mention}\n'
                                           f'Demonstrate organizational ability to get promoted to CPT!')
            elif new_role.name == 'Captain':
                scum = self.client.get_user(377177416751251487)
                rem_role = discord.utils.get(after.guild.roles, name='Lieutenant')
                await after.remove_roles(rem_role)
                await self.update_member_nick(None, after)
                await general_channel.send(f'{after.mention} has been promoted to {new_role}!\n'
                                           f'Promotes Flight Officers to Lieutenants as a group\n'
                                           f'Assassinate {scum.mention} to take the Commanders throne!')
            else:
                await self.update_member_nick(None, after)
        else:
            await self.update_member_nick(None, after)

    # Commands
    @commands.command()
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 0):
        """Mass clear messages"""
        await ctx.channel.purge(limit=amount + 1)
        await ctx.send(f'{amount} messages cleared by {ctx.message.author.mention}')

    @clear.error
    async def clear_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send('Sorry you lack the required erasers for this command!')
        else:
            print(error)

    @commands.command()
    @commands.has_any_role('Commander', 'Captain', 'Lieutenant')
    async def promote(self, ctx, member: discord.Member, *, role: str):
        """Promote a member to a rank"""
        role_dict = helper.get_config("role_dict")
        guild_role = None
        for key in role_dict.keys():
            if role.lower() in role_dict[key]:
                guild_role = key
                break
        if guild_role:
            if guild_role == 'Cadet':
                guild = self.client.get_guild(helper.get_config('guild_id'))
                intro_channel = discord.utils.get(guild.text_channels, name='introductions')
                await ctx.send(f'{ctx.author.mention}, target user will be promoted to Cadet when they post in {intro_channel.mention}.')
            else:
                guild_role = discord.utils.get(member.guild.roles, name=guild_role)
                if ctx.author.top_role > guild_role:
                    await member.add_roles(guild_role)
                else:
                    await ctx.send(f'{ctx.author.mention} you cannot promote to target rank!')
        else:
            await ctx.send('Error, no matching rank!')

    @promote.error
    async def promote_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You do not have authority to promote!')
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('You are missing arguments for this command! $promote @mention (Role)')
        else:
            print(error)

    @commands.command()
    async def update_member_nick(self, ctx, member: discord.Member = None):
        """Manual prefix update on nickname"""
        prefix, fo_num, retired = '', '', ''
        if member is None:
            member = ctx.author
        member_roles = member.roles
        guild_roles = member.guild.roles
        if discord.utils.get(guild_roles, name='Commander') in member_roles:
            return
        elif discord.utils.get(guild_roles, name='Captain') in member_roles:
            prefix = '[Cpt-{0}{1}]'
        elif discord.utils.get(guild_roles, name='Lieutenant') in member_roles:
            prefix = '[Lt-{0}{1}]'
        elif discord.utils.get(guild_roles, name='Flight Officer') in member_roles:
            prefix = '[FO-{0}{1}]'
        elif discord.utils.get(guild_roles, name='Cadet') in member_roles:
            prefix = '[Cdt]'
        elif discord.utils.get(guild_roles, name='Citizen') in member_roles:
            return
        if discord.utils.get(guild_roles, name='Retired') in member_roles:
            retired = ' (Ret.)'

        fo = await helper.get_roster(self, 'fo', member.id)
        if fo is not None:
            prefix = prefix.format(str(fo).zfill(3), retired)
        else:
            if prefix != '[Cdt]':
                prefix = prefix.format('?', retired)
        before_nick = member.nick if member.nick is not None else member.name
        index = before_nick.find(']')
        before_nick = prefix + ' ' + (before_nick[index + 1:].strip() if index > 0 else before_nick)
        after_nick = str(before_nick).lstrip()
        if len(after_nick) > 32:
            # print(f'Nickname is {len(after_nick)} characters for: {after_nick}')
            bot_commands_channel = discord.utils.get(member.guild.text_channels, name='bot-commands')
            await bot_commands_channel.send(
                f'Nickname for {member.display_name} is too long at {len(after_nick)} characters!')
        else:
            try:
                await member.edit(nick=after_nick)
            except:
                print('Error in update_nick for member:', member.display_name)

    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain', 'Lieutenant')
    async def set_fo(self, ctx, user: discord.Member, new_fo: int):
        general_channel = discord.utils.get(ctx.guild.text_channels, name='general')
        previous_id = await helper.get_roster(self, 'discord_uid', new_fo)
        if new_fo == 420:
            await ctx.send(f"Unless you verify you are Snoop Dogg, you cannot claim 420.")
        else:
            if previous_id == 0:
                # Remove other claims of FO before assignment
                prev_fo = await helper.get_roster(self, 'fo', user.id)
                if prev_fo is not None:
                    await helper.set_fo(self, prev_fo, 0)
                    await general_channel.send(f'Number {prev_fo} has opened up!')
                # Claim FO
                await helper.set_fo(self, new_fo, user.id)
                if user.id == ctx.author.id:
                    await general_channel.send(f'{user.mention} has claimed number {new_fo}!')
                else:
                    await ctx.send(f'Number {new_fo} assigned to {user.mention}')
                await self.update_member_nick(ctx, user)
                await self.update_roster()
            elif previous_id == user.id:
                if user.id == ctx.author.id:
                    await ctx.send(f'{user.mention}, you already own number {new_fo}!')
                else:
                    await ctx.send(f'{user.mention} already owns number {new_fo}!')
            elif previous_id is None:
                await ctx.send(f'That is not a registered number!')
            elif previous_id != 0:
                previous_member = ctx.guild.get_member(previous_id)
                await ctx.send(f'Number {new_fo} is already assigned to {previous_member.nick}!')
            else:
                await ctx.send(f'You found a bug in the claim command!')

    @commands.command()
    @commands.has_role('Active')
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain', 'Lieutenant', 'Flight Officer')
    async def claim(self, ctx, new_fo: int):
        """Claim a FO #"""
        await self.set_fo(ctx, ctx.author, new_fo)

    @claim.error
    async def claim_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('Please include requested FO number after command.')
        elif isinstance(error, commands.MissingAnyRole):
            await ctx.send('You must be FO or higher rank to claim a number!')
        elif isinstance(error, commands.MissingRole):
            await ctx.send('You must have Active role to claim a number!\n'
                'Maintain activity through text or voice channels.')
        else:
            print(error)

    @commands.command()
    @commands.has_any_role('GONK DROID', 'Droid Engineer', 'Commander', 'Captain')
    async def release(self, ctx, fo: int):
        """Release a FO #"""
        general_channel = discord.utils.get(ctx.guild.text_channels, name='general')
        previous_id = await helper.get_roster(self, 'discord_uid', fo)
        if previous_id == 0:
            await general_channel.send(f'FO {fo} is unclaimed!')
        else:
            await helper.set_fo(self, fo, 0)
            discord_member = ctx.guild.get_member(previous_id)
            await self.update_member_nick(discord_member)
            await general_channel.send(f'FO {fo} has been released!')
            await self.update_roster()

    @release.error
    async def release_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You do not have authority to release FO numbers! Please contact someone of Cpt+ rank.')
        else:
            print(error)

    @commands.command()
    async def fo(self, ctx, fo: int = None):
        """Check FO number"""
        if fo is None:
            # Return self
            current_fo = await helper.get_roster(self, 'fo', ctx.author.id)
            if current_fo is not None:
                await ctx.send(f'{ctx.author.nick} is FO {current_fo}!')
            else:
                await ctx.send(f'{ctx.author.nick} has no FO number!')
        else:
            # Return at that number
            previous_id = await helper.get_roster(self, 'discord_uid', fo)
            if previous_id is None:
                await ctx.send(f'That is not a registered FO number!')
            elif previous_id != 0:
                discord_member = ctx.guild.get_member(previous_id)
                await ctx.send(f'FO {fo} is claimed by {discord_member.nick}!')
            elif previous_id == 0:
                await ctx.send(f'FO {fo} is unclaimed!')
            else:
                await ctx.send(f'You found a bug in the FO command!')

    async def create_roster_list(self, guild: discord.Guild):
        # Discord Message Body limit is 2000 characters
        # Change roster into embed with pages?
        roster = await helper.get_whole_roster(self)
        master_list = []
        roster_message_list = ['', 'ROSTER LIST:']
        for num, discord_id in roster:
            member = guild.get_member(discord_id)
            if member is None:
                roster_message_list.append(f'-')
            else:
                roster_message_list.append(f'\t\t{member.nick}')
            roster_message = '\n'.join(roster_message_list)
            if num % 50 == 0:
                master_list.append(roster_message)
                roster_message_list = ['', 'ROSTER LIST:']
        master_list.append(roster_message)
        return master_list

    @commands.command()
    async def update_roster(self, ctx=None):
        """Manual roster update"""
        guild = self.client.get_guild(helper.get_config('guild_id'))
        roster_channel = guild.get_channel(777241135051440149)
        message_list = await roster_channel.history(oldest_first=True).flatten()
        roster_master_list_of_lists = await self.create_roster_list(guild)

        async def send_complete_roster():
            for idx, roster_message in enumerate(roster_master_list_of_lists):
                await roster_channel.send(f'{roster_message}')

        for idx2, roster_message2 in enumerate(roster_master_list_of_lists):
            try:
                message = message_list[idx2]
            except IndexError:
                await roster_channel.purge()
                await send_complete_roster()
                break
            else:
                await message.edit(content=roster_message2)

    @commands.command()
    async def roster(self, ctx):
        """Links to the roster channel"""
        roster_channel = discord.utils.get(ctx.guild.text_channels, name='roster')
        return await ctx.send(f'Here you go: {roster_channel.mention}')

    @commands.command()
    async def serverinvite(self, ctx):
        """PM a server invite code to invoker"""
        invite = await ctx.channel.create_invite(max_uses=0, unique=True)
        await ctx.author.send("Your invite URL is {}".format(invite.url))
        await ctx.send("Check Your Dm's :wink: ")

    @commands.command()
    async def serverinfo(self, ctx):
        """Displays info about the server"""
        guild = ctx.guild
        roles = [x.name for x in guild.roles]
        role_length = len(roles)

        if role_length > 50:  # Just in case there are too many roles...
            roles = roles[:50]
            roles.append('>>>> Displaying[50/%s] Roles' % len(roles))

        roles = ', '.join(roles)
        channelz = len(guild.channels)
        dt = str(guild.created_at).split(' ')[0]

        join = discord.Embed(description='%s ' % (str(guild)), title='Server Name', colour=0xFFFF)
        join.set_thumbnail(url=guild.icon_url)
        join.add_field(name='__Owner__', value=str(guild.owner) + '\n' + str(guild.owner.id))
        join.add_field(name='__ID__', value=str(guild.id))
        join.add_field(name='__Member Count__', value=str(guild.member_count))
        join.add_field(name='__Text/Voice Channels__', value=str(channelz))
        join.add_field(name='__Roles (%s)__' % str(role_length), value=roles)
        join.set_footer(text='Created: %s' % dt)

        return await ctx.send(embed=join)

    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain', 'Lieutenant')
    async def warn(self, ctx, user, *, reason='None'):
        """Warns a Member"""
        em = discord.Embed(color=0xff0000)
        em.add_field(name='Warning', value="Galactic Senate finds you at fault!")
        em.add_field(name='User', value=user)
        em.add_field(name='Reason', value=reason)
        em.set_footer(text='Warned At: %s' % datetime.datetime.now())
        await ctx.send(embed=em)
        await ctx.message.delete()

    @warn.error
    async def warn_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You do not have authority to warn!')
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send('You are missing arguments for this command! $warn @mention [Reason]')
        else:
            print(error)

    @commands.command()
    async def guide(self, ctx):
        """Returns the gray squadron orientation guide as an attachment"""
        guide = discord.File('assets/pdf/Orientation.pdf')
        await ctx.send(file=guide, content='Gray Squad Orientation Guide')

    @guide.error
    async def guide_error(self, ctx, error):
        await ctx.send('There is an error with the guide!')
        print(error)

    # TODO: This command cannot be used in private messages.
    # TODO: Auto-delete and add new comments to about section
    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain', 'Lieutenant')
    async def upload_guide(self, ctx):
        """Function to upgrade the gray orientation guide stored on the server"""
        attachments = ctx.message.attachments
        if len(attachments) == 1:
            await attachments[0].save('assets/pdf/Orientation.pdf')
            await ctx.send('Attachment saved!')
        else:
            await ctx.send('There was no attachment!')

    @upload_guide.error
    async def upload_guide_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You do not have authority to upload guide!')
        else:
            await ctx.send('There is an error with the guide upload!')
            print(error)

    @commands.command()
    async def bantha(self, ctx):
        """Returns the bantha guide as an attachment"""
        guide = discord.File('assets/pdf/Bantha.pdf')
        await ctx.send(file=guide, content='Bantha Cub Guide')

    @bantha.error
    async def bantha_error(self, ctx, error):
        await ctx.send('There is an error with the guide!')
        print(error)

    # TODO: This command cannot be used in private messages.
    # TODO: Auto-delete and add new comments to about section
    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain', 'Lieutenant')
    async def upload_b_guide(self, ctx):
        """Function to upgrade the bantha guide stored on the server"""
        attachments = ctx.message.attachments
        if len(attachments) == 1:
            await attachments[0].save('assets/pdf/Bantha.pdf')
            await ctx.send('Attachment saved!')
        else:
            await ctx.send('There was no attachment!')

    @upload_b_guide.error
    async def upload_b_guide_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You do not have authority to upload guide!')
        else:
            await ctx.send('There is an error with the guide upload!')
            print(error)

    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain', 'Lieutenant')
    async def assign_mentor(self, ctx, mentor: discord.Member, mentee: discord.Member):
        """Assign a mentor to a mentee"""
        guild = self.client.get_guild(helper.get_config('guild_id'))
        mentor_uid = mentor.id
        mentee_uid = mentee.id
        if discord.utils.get(guild.roles, name='Lieutenant') not in mentor.roles:
            await ctx.send(f'{mentor.nick} can not take on a mentee!')
        elif discord.utils.get(guild.roles, name='Cadet') not in mentee.roles:
            await ctx.send(f'{mentee.nick} is not a Cadet!')
        # TODO: Remove existing mentor from mentee
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute('INSERT INTO gray.mentor (mentor_uid, mentee_uid) '
                                         'VALUES ($1, $2)'
                                         'ON CONFLICT (mentee_uid) DO UPDATE SET mentor_uid = $1', mentor_uid,
                                         mentee_uid)
                # TODO: Success/error message

    @assign_mentor.error
    async def assign_mentor_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You do not have authority to assign mentors!')
        else:
            await ctx.send('There is an error with the assign mentors function!')
            print(error)

    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain', 'Lieutenant')
    async def clear_mentee(self, ctx, mentee: discord.Member):
        """Remove mentee from mentor-mentee table"""
        mentee_uid = mentee.id
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute('DELETE FROM gray.mentor WHERE mentee_uid = $1', mentee_uid)
                # TODO: Success/error message

    @clear_mentee.error
    async def clear_mentee_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You do not have authority to clear mentees!')
        else:
            await ctx.send('There is an error with the clear mentees function!')
            print(error)

    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Cadet')
    async def get_mentor(self, ctx, mentee: discord.Member = None):
        """Get mentor for self or specified user"""
        if mentee is None:
            mentee = ctx.author
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                mentor_uid = await connection.fetchval('SELECT mentor_uid FROM gray.mentor WHERE mentee_uid = $1',
                                                       mentee.id)
        if mentor_uid is not None:
            mentor_member = ctx.guild.get_member(mentor_uid)
            await ctx.send(f'Your assigned mentor is: {mentor_member.mention}')
        else:
            await ctx.send(f'You do not have an assigned mentor! How did this happen?')

    @get_mentor.error
    async def get_mentor_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('Only Cadets have mentors!')
        else:
            print(error)

    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain', 'Lieutenant')
    async def get_mentees(self, ctx, *, mentor: discord.Member = None):
        """Get mentees for self or specified user"""
        if mentor is None:
            mentor = ctx.author
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                mentee_uid_list = await connection.fetch('SELECT mentee_uid FROM gray.mentor WHERE mentor_uid = $1',
                                                         mentor.id)
        if mentee_uid_list is not None:
            # Create string of mentees
            mentee_list = ['', 'MENTEE LIST:']
            for mentee_uid in mentee_uid_list:
                member = ctx.guild.get_member(mentee_uid[0])
                if member is None:
                    async with self.client.pool.acquire() as connection:
                        async with connection.transaction():
                            await connection.execute('DELETE FROM gray.mentor WHERE mentee_uid = $1', mentee_uid[0])
                else:
                    mentee_list.append(f'\t\t{member.display_name}')
            mentee_message = '\n'.join(mentee_list)
            await ctx.send(mentee_message)
        else:
            await ctx.send(f'You do not have any assigned mentees!')

    @get_mentees.error
    async def get_mentees_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('Your rank does not have mentees!')
        else:
            print(error)

    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain')
    async def set_team_description(self, ctx, role: discord.Role, *, description: str):
        """Function to set the description for a team"""
        role_uid = role.id
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("""INSERT INTO gray.teaminfo (role_uid, team_desc)
                                            VALUES ($1, $2)
                                            ON CONFLICT (role_uid) DO UPDATE SET team_desc = $2""",
                                         role_uid,
                                         description)

    @set_team_description.error
    async def set_team_description_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You must be Cpt+ to set team description!')
        elif isinstance(error, commands.RoleNotFound):
            await ctx.send('Please mention a role as the first argument.')
        else:
            print(error)

    async def get_team_description(self, role_uid: int):
        """Function get team description for a specific role"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                team_desc = await connection.fetchval("""SELECT team_desc FROM gray.teaminfo
                                                           where role_uid = $1""",
                                                      role_uid)
        if team_desc is None:
            team_desc = 'No description.'
        return team_desc

    @commands.command()
    @commands.has_any_role('Droid Engineer', 'Commander', 'Captain')
    async def set_team_emblem(self, ctx, role: discord.Role, *, emblem_link: str):
        """Function to set the description for a team"""
        role_uid = role.id
        emblem_link = emblem_link.replace('"', '').replace("'", "")
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute("""INSERT INTO gray.teaminfo (role_uid, team_emblem)
                                            VALUES ($1, $2)
                                            ON CONFLICT (role_uid) DO UPDATE SET team_emblem = $2""",
                                         role_uid,
                                         emblem_link)

    @set_team_emblem.error
    async def set_team_emblem_error(self, ctx, error):
        if isinstance(error, commands.MissingAnyRole):
            await ctx.send('You must be Cpt+ to set team emblem!')
        elif isinstance(error, commands.RoleNotFound):
            await ctx.send('Please mention a role as the first argument.')
        else:
            print(error)

    async def get_team_emblem(self, role_uid: int):
        """Function get team emblem for a specific role"""
        async with self.client.pool.acquire() as connection:
            async with connection.transaction():
                emblem_link = await connection.fetchval("""SELECT team_emblem FROM gray.teaminfo
                                                           where role_uid = $1""",
                                                        role_uid)
        if emblem_link is None:
            emblem_link = 'https://cdn.discordapp.com/attachments/800431166997790790/837390154242326538/unknown.png'
        return emblem_link

    @commands.command(aliases=['team'])
    async def teams(self, ctx):
        """Displays paginated embed of teams if plural, users team if singular"""
        if '$TEAMS' in ctx.message.content.upper():
            roles = [r for r in ctx.guild.roles if 'Team' in r.name and 'Leader' not in r.name]
        else:
            roles = [r for r in ctx.author.roles if 'Team' in r.name and 'Leader' not in r.name]
        if len(roles) > 0:
            team_list = []
            for role in roles:
                members = role.members
                desc = await self.get_team_description(role.id)
                emblem = await self.get_team_emblem(role.id)
                for idx, member in enumerate(members):
                    if idx == 0:
                        team_list.append(
                            gonk_menus.CustomDic(key=role.name, value=[member.display_name, role.name, role.color,
                                                                       desc, emblem]))
                    else:
                        team_list.append(
                            gonk_menus.CustomDic(key=role.name, value=[member.display_name, 0, 0, 0, 0]))
            menu = menus.MenuPages(source=gonk_menus.TeamMenu(ctx, team_list, key=lambda t: t.key),
                                   clear_reactions_after=True)
            await menu.start(ctx)
        else:
            await ctx.send('You are on no teams!')

    @teams.error
    async def teams_error(self, ctx, error):
        print(error)

    # Background Tasks
    @tasks.loop(seconds=600, reconnect=True)
    async def update_nick(self):
        """Background task to upgrade name with proper prefix"""
        guild = self.client.get_guild(helper.get_config('guild_id'))
        cdt = discord.utils.get(guild.roles, name='Cadet').members
        fo = discord.utils.get(guild.roles, name='Flight Officer').members
        lt = discord.utils.get(guild.roles, name='Lieutenant').members
        cpt = discord.utils.get(guild.roles, name='Captain').members
        merged = list(set(cdt + fo + lt + cpt))
        for member in merged:
            if member.id != 195747311136145409:
                await self.update_member_nick(None, member)

    @tasks.loop(seconds=600, reconnect=True)
    async def inactive(self):
        """Remove FO# from inactive members"""
        guild = self.client.get_guild(helper.get_config('guild_id'))
        fo = discord.utils.get(guild.roles, name='Flight Officer').members
        general_channel = discord.utils.get(guild.text_channels, name='general')
        for member in fo:
            if discord.utils.get(member.roles, name='Active') not in member.roles:
                current_fo = await helper.get_roster(self, 'fo', member.id)
                if current_fo is not None:
                    # print(f'Remove FO from: {member.display_name} who has {current_fo}')
                    await helper.set_fo(self, current_fo, 0)
                    await self.update_member_nick(None, member)
                    await general_channel.send(f'FO {current_fo} has been released from {member.mention}!')
                    await self.update_roster()
                    await member.send(f'Your FO#: {current_fo} has been released due to inactivity!'
                                      f'Maintain activity through text or voice channels!'
                                      f'Reclaim your FO# by using the $claim # command in the discord!')


def setup(client):
    client.add_cog(Admin(client))
