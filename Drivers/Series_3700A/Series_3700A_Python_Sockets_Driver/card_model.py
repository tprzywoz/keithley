class ClosedDict(dict):
    def __setitem__(self, key, value):
        if key not in self:
            raise KeyError("ClosedDict cannot get new keys")
        dict.__setitem__(self, key, value)

class GenericModel():
    '''
    Each function accepts 3 formats of argument:
    1: int - single channel
    2: int int - range of channels from first int to second
    3: list(int) - list of channels
    '''
    def __init__(self, controller, slot):
        self.controller = controller
        self.slot = slot

    def parser(func):
        def wrapper(self, *args, **kwargs):
            if self.__class__.__name__ == "Model_3732_4B":
                multiplier = 10_000
            else:
                multiplier = 1_000
            if len(args) > 1:  # Range
                if len(args) > 2:
                    print("Unsupported format of data: more than 2 arguments. Check GenericModel")
                    exit(-2)
                if func.__name__ == "open":
                    for i in range(args[0], args[1]+1):
                        self.channels[i] = False
                elif func.__name__ == "close":
                    for i in range(args[0], args[1]+1):
                        self.channels[i] = True
                func(self, str(self.slot*multiplier + args[0]) + ":" + str(self.slot*multiplier + args[1]))
            elif len(args) == 1:
                if isinstance(args[0], int):
                    if func.__name__ == "open":
                        self.channels[args[0]] = False
                    elif func.__name__ == "close":
                        self.channels[args[0]] = True
                    func(self, str(self.slot*multiplier + args[0]))
                elif isinstance(args[0], list):
                    channels = str()
                    for ch in args[0]:
                        channels += (str(self.slot * multiplier + ch)+", ")
                        if func.__name__ == "open":
                            self.channels[ch] = False
                        elif func.__name__ == "close":
                            self.channels[ch] = True
                    func(self, channels[:-2])
                else:
                    print("Unsupported format of data: {}. Check GenericModel".format(args[0]))
                    exit(-2)
        return wrapper

    @parser
    def close(self, cmd):
        self.controller.Close(cmd)

    @parser
    def open(self, cmd):
        self.controller.Open(cmd)

    @parser
    def set_forbidden(self, cmd):
        self.controller.SetForbidden(cmd)

    @parser
    def clear_forbidden(self, cmd):
        self.controller.ClearForbidden(cmd)

    @parser
    def open_backplane(self, cmd):
        raise NotImplemented

    @parser
    def safe_close(self, cmd):
        raise NotImplemented



class GenericDual(GenericModel):
    '''
    __init__ function of Generic Model of Dual cards

    :param controller: KEI3706A object to control relays
    :param slot: integer slot number in 3700 Series device
    :param allow_sc (list[bool, bool]): allow short circuit in bank X - True if parallel close is allowed
    '''
    def __init__(self, controller, slot, allow_sc=[False, False]):
        GenericModel.__init__(self, controller, slot)
        self.allow_sc = allow_sc



# class MatrixParameters():
#     def __init__(self, rows, columns, allow_row_sc, allow_column_sc):


class GenericMatrix(GenericModel):
    '''
    rows_nb, cols_nb: number of rows and columns per single bank
    allow_sc: list of bool pairs. Single pair: allow short circuit on rows, on columns. Number of pairs = number of banks
    '''
    def __init__(self, controller, slot, banks_nb, rows_nb, cols_nb, allow_sc):
        # channel numbers
        GenericModel.__init__(self, controller, slot)
        channel_numbers = [bank * 1000 + row * 100 + col for bank in range(1, banks_nb+1)
                                                          for row in range(1, rows_nb+1)
                                                         for col in range(1, cols_nb+1)]
        self.channels = ClosedDict({i: False for i in channel_numbers})
        self.allow_sc = allow_sc
        self.rows_nb = rows_nb
        self.cols_nb = cols_nb


class Model_3732_4B(GenericMatrix):
    def __init__(self, controller, slot, allow_sc):
        GenericMatrix.__init__(self, controller, slot, 4, 4, 28, allow_sc)
        backplane_channels = ClosedDict({i: False for i in range(10911, 10919)})
        self.channels.update(backplane_channels)

    @staticmethod
    def channel_number(bank, row, col):
        return bank * 1000 + row * 100 + col

    def open_bank(self, bank):
        channels = [bank * 1000 + row * 100 + col for row in range(1,5) for col in range(1,29)]
        self.open(channels)

    def open_backplane(self, forbid=True):
        self.open(10911, 10918)
        if forbid:
            self.set_forbidden(10911, 10918)

    def open_all(self):
        for i in range(4):
            self.open_bank(i+1)
        self.open_backplane()

    '''
       Change active channel. Requires exactly 0 or 1 channel already closed which cannot be closed parallel 
       with new one. Method will open it and close new channel given in argument.
       '''

    def switch(self, bank, row, column):
        self.switch_channel(self.channel_number(bank, row, column))

    def switch_channel(self, channel):
        # check if argument is single channel
        if not isinstance(channel, int):
            print("switch_channel method takes only int argument")
            exit(1)
        active_channel = list()
        # If check for active channel to open it
        col = channel % 100
        row = channel % 1000 // 100
        bank = channel // 1000
        # backplane switch
        if bank == 0:
            print("WARNING: switching backplane channel will open all other backplane channels.")
            self.controller.open_all_backplanes()
            self.clear_forbidden(channel)
            super().close(channel)
            return
        else:
            # check row short circuits:
            if not self.allow_sc[bank][0]:
                for i in range(1, self.cols_nb + 1):
                    if self.channels[self.channel_number(bank=bank, row=row, col=i)]:
                        active_channel.append(self.channel_number(bank= bank, row=row, col=i))
            # check col short circuits:
            if not self.allow_sc[bank][1]:
                for i in range(1, self.rows_nb + 1):
                    if self.channels[self.channel_number(bank=bank, row=i, col=col)]:
                        active_channel.append(self.channel_number(bank= bank, row=i, col=col))
        # Switch function works only as: open one, close another   OR nothing to open, close one
        if len(active_channel) > 1:
            print("switch_channel: exactly one channel should be already active. Current active channels: {}".format(
                active_channel))
            exit(1)

        # Open previous channel
        if len(active_channel) == 1:
            self.open(active_channel[0])
            # Set old channel forbidden to close and clear forbidden for new one
            self.set_forbidden(active_channel[0])
        # There is no active channel: whole row/column in bank should be forbidden
        else:
            to_be_forbidden = list()
            # add forbidden switches in row
            if not self.allow_sc[bank][0]:
                for i in range(1, self.cols_nb + 1):
                    to_be_forbidden.append(self.channel_number(bank=bank, row=row, col=i))
            if not self.allow_sc[bank][1]:
                for i in range(1, self.rows_nb + 1):
                    to_be_forbidden.append(self.channel_number(bank=bank, row=i, col=col))
            to_be_forbidden.remove(channel)
            self.set_forbidden(to_be_forbidden)
        self.clear_forbidden(channel)
        # Close new channel, use GenericModel method - safety has already been checked
        super().close(channel)

    def close(self, channels):
        '''
        Method closes channel or channels (if it is possible - method will check permission - not supported for backplane switches)
        Args:
            channels: int or list of ints with number of channels to close (without slot number).

        Returns:

        '''
        if isinstance(channels, int):
            channels = [channels]
        for channel in channels:
            col = channel % 100
            row = channel % 1000 // 100
            bank = channel // 1000
            # backplane switch
            if bank == 0:
                modify_forbidden = False
            else:
                modify_forbidden = False
                # check row short circuits:
                if not self.allow_sc[bank][0]:
                    modify_forbidden = True
                    for i in range(1, self.cols_nb+1):
                        if self.channels[self.channel_number(bank=bank, row=row, col=i)]:
                            raise (PermissionError("Another channel already closed - forbidden to close this channel"))
                # check col short circuits:
                if not self.allow_sc[bank][1]:
                    modify_forbidden = True
                    for i in range(1, self.rows_nb+1):
                        if self.channels[self.channel_number(bank=bank, row=i, col=col)]:
                            raise (PermissionError("Another channel already closed - forbidden to close this channel"))

            self.channels[channel] = True # change value here (not at the close) to proper check next channels
            # Block all other switches in bank if short circuit not allowed:
            if modify_forbidden:
                to_be_forbidden = list()
                #add forbidden switches in row
                if not self.allow_sc[bank][0]:
                    for i in range(1, self.cols_nb + 1):
                        to_be_forbidden.append(self.channel_number(bank=bank, row=row, col=i))
                if not self.allow_sc[bank][1]:
                    for i in range(1, self.rows_nb + 1):
                        to_be_forbidden.append(self.channel_number(bank=bank, row=i, col=col))
                to_be_forbidden.remove(channel)
                self.set_forbidden(to_be_forbidden)
        super().close(channels)




class Model_3723_2B(GenericDual):
    first_channel = 1
    last_channel = 60
    first_backplane_channel = 911
    def __init__(self, controller, slot, allow_sc=[False, False]):
        GenericDual.__init__(self, controller, slot, allow_sc)
        channel_numbers = [i for i in range(1,61)] + [i for i in range(911, 917)] + [i for i in range(921, 927)]
        self.channels = ClosedDict({i: False for i in channel_numbers})

    def open_bank0(self):
        self.open(1, 30)

    def open_bank1(self):
        self.open(31, 60)

    def open_bank1_backplane(self, forbid=True):
        self.open(911, 916)
        if forbid:
            self.set_forbidden(911, 916)

    def open_bank2_backplane(self, forbid=True):
        self.open(921, 926)
        if forbid:
            self.set_forbidden(921, 926)

    def open_backplane(self, forbid=True):
        self.open_bank1_backplane(forbid)
        self.open_bank2_backplane(forbid)

    def open_all(self):
        self.open_bank0()
        self.open_bank1()
        self.open_backplane()

    '''
    Change active channel. Requires exactly 0 or 1 channel already closed which cannot be closed parallel 
    with new one. Method will open it and close new channel given in argument.
    '''
    def switch_channel(self, channel):
        # check if argument is single channel
        if not isinstance(channel, int):
            print("switch_channel method takes only int argument")
            exit(1)
        active_channel = list()
        # If in first bank: check first bank if allow_sc is false and look for single closed channel
        if 1 <= channel <31:
            first = 1
            last = 30
            if self.allow_sc[0]:
                print("switch_channel: to use this method, current bank cannot have attribute: allow_sc True")
                exit(1)
            for i in range(1, 31):
                if self.channels[i]:
                    active_channel.append(i)
        # If in second bank: check second bank if allow_sc is false and look for single closed channel
        elif 31 <= channel < 61:
            first = 31
            last = 60
            if self.allow_sc[1]:
                print("switch_channel: to use this method, current bank cannot have attribute: allow_sc True")
                exit(1)
            for i in range(31, 61):
                if self.channels[i]:
                    active_channel.append(i)
        elif (911 <= channel <= 916) or (921 <= channel <= 926):
            print("WARNING: switching backplane channel will open all other backplane channels.")
            self.controller.open_all_backplanes()
            self.clear_forbidden(channel)
            super().close(channel)
            return
        else:
            raise(IndexError("Card 3723 channels: 1-60 911-916 921-926"))
        # Switch function works only as: open one, close another   OR nothing to open, close one
        if len(active_channel) > 1:
            print("switch_channel: exactly one channel should be already active. Current active channels: {}".format(active_channel))
            exit(1)

        # Open previous channel
        if len(active_channel) == 1:
            self.open(active_channel[0])
            # Set old channel forbidden to close and clear forbidden for new one
            self.set_forbidden(active_channel[0])
        # There is no active channel: whole bank need to be forbidden
        else:
            self.set_forbidden(first, last)
        self.clear_forbidden(channel)
        # Close new channel, use GenericModel method - safety has already been checked
        super().close(channel)

    '''
    Method closes channel or channels (if it is possible - method will check permission - not supported for backplane switches)
    '''
    def close(self, channels):
        if isinstance(channels, int):
            channels = [channels]
        for channel in channels:
            if 1 <= channel <31:
                if not self.allow_sc[0]:    #if not allowed parallel check bank
                    first = 1
                    last = 30
                    modify_forbidden = True
                    for i in range(1, 31):
                        if self.channels[i]:
                            raise(PermissionError("Another channel already closed - forbidden to close this channel"))
            elif 31 <= channel < 61:        #if not allowed parallel check bank
                if not self.allow_sc[1]:
                    first = 31
                    last = 60
                    modify_forbidden = True
                    for i in range(31, 61):
                        if self.channels[i]:
                            raise(PermissionError("Another channel already closed - forbidden to close this channel"))
            elif (911 <= channel <= 916) or (921 <= channel <= 926):
                modify_forbidden = False
                continue
            else:
                raise(IndexError("Card 3723 channels: 1-60 911-916 921-926"))
            self.channels[channel] = True # change value here (not at the close) to proper check next channels
            # Block all other switches in bank if short circuit not allowed:
            if modify_forbidden:
                to_be_forbidden = [i for i in range(first, last+1)]
                to_be_forbidden.remove(channel)
                self.set_forbidden(to_be_forbidden)
        super().close(channels)



