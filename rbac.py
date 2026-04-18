# def is_admin(role):
#     return role == 'Admin'

# def is_student(session):
#     return session.get('sub_role') == 'Student'

# def is_staff(session):
#     return session.get('sub_role') == 'Staff'

# def get_member_id(session):
#     return session.get('member_id')

# def get_sub_id(session):
#     return session.get('sub_id')

def is_admin(role):
    """Pass session.get('role')"""
    return role == 'Admin'

def is_student(member_role):
    """Pass session.get('member_role')"""
    return member_role == 'Student'

def is_staff(member_role):
    """Pass session.get('member_role')"""
    return member_role == 'Staff'